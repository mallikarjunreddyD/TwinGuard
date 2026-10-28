"""Only authenticated service identity + independent source registry authorize data."""

import hashlib
from datetime import timedelta
from sqlalchemy import select, func
from .contracts import Envelope, SourceRegistration, now
from .storage import inbox, observations, jobs, get, put, audit, enqueue, emit

MAX_MESSAGE = 128 * 1024


def topic(source, site="plant-01", kind="observation"):
    channel = "iot" if kind == "observation" else "inspection"
    suffix = "observations" if kind == "observation" else "manifests"
    return f"twinguard/v1/{site}/{channel}/{source}/{suffix}"


def scheduling_priority(observation, registration, effective, received):
    if (
        observation.measurement_type not in ["pressure", "temperature"]
        or registration.clock_quality != "synchronized"
    ):
        return 10
    from .worker import policy
    from twinguard.fusion.adapters import engineering_limit
    from twinguard.fusion.models import ProcessingRecord

    p = policy()
    accepted = (
        ["verified", "assumed_simulation"]
        if p.deployment_mode == "illustrative_simulation"
        else ["verified"]
    )
    if registration.calibration_status not in accepted:
        return 10
    effective_observation = observation.model_copy(
        update={"acquired_at": effective, "received_at": received, "processed_at": None}
    )
    done = now()
    record = ProcessingRecord(
        source_id=observation.observation_id,
        received_at=received,
        processed_at=done,
        available_at=done,
        basis="recorded",
        clock_quality=registration.clock_quality,
        rationale="Scheduling hint only, evaluated by the existing engineering-limit adapter. Worker/F1 independently requalify the observation.",
    )
    evidence = engineering_limit(effective_observation, record, p)
    return 0 if evidence and evidence.authoritative_limit and evidence.finding == "positive" else 10


def ingest(db, raw, authenticated_identity, received_topic, artifact_store=None):
    received = now()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        if len(raw) > MAX_MESSAGE:
            raise ValueError("oversized_message")
        env = Envelope.model_validate_json(raw)
        with db.begin() as c:
            source = get(c, "source", env.source_id, lock=True)
            if not source:
                raise ValueError("unregistered_source")
            reg = SourceRegistration.model_validate(source)
            if not reg.active or authenticated_identity != reg.transport_identity:
                raise ValueError("unauthorized_transport_identity")
            if (
                received_topic != topic(env.source_id, env.site_id, env.kind)
                or env.site_id != reg.site_id
            ):
                raise ValueError("unauthorized_topic")
            if env.configuration_reference != reg.configuration_reference:
                raise ValueError("unsupported_configuration")
            if env.emitted_at.tzinfo is not None and env.emitted_at > received + timedelta(
                seconds=2
            ):
                raise ValueError("future_publisher_timestamp")
            if (
                env.emitted_at.tzinfo is None
                or abs((received - env.emitted_at).total_seconds()) > 3600
            ):
                raise ValueError("invalid_publisher_time")
            previous = (
                c.execute(select(inbox).where(inbox.c.id == env.message_id)).mappings().first()
            )
            previous = previous or get(c, "archive", env.message_id)
            if previous:
                if previous["digest"] != digest:
                    raise ValueError("conflicting_message_identity")
                audit(c, "duplicate_delivery", message_id=env.message_id)
                return {"status": "duplicate", "id": env.message_id}
            depth = c.execute(
                select(func.count()).select_from(jobs).where(jobs.c.status == "pending")
            ).scalar_one()
            if depth >= 10000:
                raise ValueError("backpressure_queue_limit")
            body = env.model_dump(mode="json")
            c.execute(
                inbox.insert().values(
                    id=env.message_id,
                    source=env.source_id,
                    digest=digest,
                    received=received.isoformat(),
                    status="accepted",
                    body=body,
                )
            )
            prior_seq = source.get(
                "last_sequence"
            )  # Registry schema is kept separate from dynamic health.
            health = get(c, "source_health", env.source_id) or {}
            prior_seq = health.get("last_sequence", prior_seq)
            if health.get("sequence_epoch") != env.sequence_epoch:
                prior_seq = None
                health["last_acquired_by_sensor"] = {}
                audit(c, "publisher_epoch_changed", source=env.source_id, epoch=env.sequence_epoch)
            health["sequence_epoch"] = env.sequence_epoch
            if prior_seq is not None and env.sequence <= prior_seq:
                audit(c, "out_of_order", message_id=env.message_id)
            elif prior_seq is not None and env.sequence > prior_seq + 1:
                audit(c, "sequence_gap", expected=prior_seq + 1, actual=env.sequence)
            if env.kind == "observation":
                obs = env.observation
                if obs is None:
                    raise ValueError("missing_observation")
                expected = reg.sensors.get(obs.sensor_id)
                if not expected or any(
                    expected[k] != getattr(obs, k) for k in ["asset_id", "unit", "measurement_type"]
                ):
                    raise ValueError("sensor_asset_unit_mismatch")
                if obs.configuration_version not in [None, reg.configuration_reference]:
                    raise ValueError("unsupported_sensor_configuration")
                effective = obs.acquired_at
                if env.mode == "simulation_replay":
                    if (
                        reg.clock_basis != "controlled_simulation_replay"
                        or obs.source_type != "synthetic"
                    ):
                        raise ValueError("untrusted_replay_clock")
                    effective = env.replay_acquired_at
                    if effective is None or effective.tzinfo is None:
                        raise ValueError("missing_replay_clock")
                if effective > received:
                    raise ValueError("future_timestamp")
                if (received - effective).total_seconds() > 86400:
                    audit(c, "delayed_observation", observation_id=obs.observation_id)
                old = c.execute(
                    select(observations.c.body).where(observations.c.id == obs.observation_id)
                ).scalar_one_or_none()
                if old is not None:
                    ignored = {"received_at", "processed_at", "delivery_status"}
                    incoming = obs.model_dump(mode="json")
                    if {k: v for k, v in old.items() if k not in ignored} != {
                        k: v for k, v in incoming.items() if k not in ignored
                    }:
                        raise ValueError("conflicting_observation_identity")
                    health.update(
                        last_received=received.isoformat(),
                        quality=obs.quality,
                        clock_quality=reg.clock_quality,
                        calibration_status=reg.calibration_status,
                    )
                    health["last_sequence"] = max(env.sequence, prior_seq or 0)
                    put(c, "source_health", env.source_id, health)
                    audit(c, "duplicate_observation", observation_id=obs.observation_id)
                    return {"status": "duplicate", "id": obs.observation_id}
                prior_acquired = health.setdefault("last_acquired_by_sensor", {}).get(obs.sensor_id)
                if prior_acquired and effective.isoformat() < prior_acquired:
                    audit(c, "out_of_order_acquisition", observation_id=obs.observation_id)
                health["last_acquired_by_sensor"][obs.sensor_id] = max(
                    effective.isoformat(), prior_acquired or effective.isoformat()
                )
                priority = scheduling_priority(obs, reg, effective, received)
                meta = {
                    "authenticated_identity": authenticated_identity,
                    "claimed_source": env.source_id,
                    "edge_received_at": received.isoformat(),
                    "effective_acquired_at": effective.isoformat(),
                    "source_clock_claim": obs.clock_quality,
                    "trusted_clock_quality": reg.clock_quality,
                    "clock_basis": reg.clock_basis,
                    "mode": env.mode,
                    "replay_rate": env.replay_rate,
                    "message_id": env.message_id,
                    "scheduling_priority": priority,
                    "calibration_status": reg.calibration_status,
                    "calibration_reference": reg.calibration_reference,
                    "publisher_emitted_at": env.emitted_at.isoformat(),
                }
                c.execute(
                    observations.insert().values(
                        id=obs.observation_id,
                        asset=obs.asset_id,
                        sensor=obs.sensor_id,
                        acquired=obs.acquired_at.isoformat(),
                        received=received.isoformat(),
                        source=env.source_id,
                        body=obs.model_dump(mode="json"),
                        metadata=meta,
                    )
                )
                enqueue(
                    c,
                    obs.observation_id,
                    "iot",
                    {"observation_id": obs.observation_id, "priority": priority},
                )
                health.update(
                    last_received=received.isoformat(),
                    last_valid=received.isoformat()
                    if obs.quality == "good"
                    else health.get("last_valid"),
                    quality=obs.quality,
                    clock_quality=reg.clock_quality,
                    calibration_status=reg.calibration_status,
                )
            else:
                if not reg.allow_inspections or artifact_store is None:
                    raise ValueError("inspection_not_authorized")
                captures = artifact_store.verify_bundle(env.artifact_sha256)
                from twinguard.core.contracts import InspectionCapture

                for capture in captures:
                    if isinstance(capture, InspectionCapture):
                        allowed = reg.capture_sensors.get(capture.sensor_id, [])
                        if not set(capture.asset_ids) <= set(allowed):
                            raise ValueError("unauthorized_inspection_sensor_asset")
                if env.mode == "simulation_replay" and (
                    reg.clock_basis != "controlled_simulation_replay"
                    or env.replay_acquired_at is None
                    or env.replay_acquired_at.tzinfo is None
                    or env.replay_acquired_at > received
                ):
                    raise ValueError("untrusted_inspection_replay_clock")
                if env.mode == "simulation_replay":
                    source_anchor = max(
                        r.acquired_at for r in captures if isinstance(r, InspectionCapture)
                    )
                    if env.replay_source_anchor_at != source_anchor:
                        raise ValueError("inspection_replay_anchor_must_match_latest_capture")
                previous_bundle = get(c, "inspection_input", env.artifact_sha256)
                if previous_bundle:
                    audit(c, "duplicate_inspection_bundle", sha256=env.artifact_sha256)
                    return {"status": "duplicate", "id": previous_bundle["job_id"]}
                put(c, "inspection_input", env.artifact_sha256, {"job_id": env.message_id})
                health.update(
                    last_received=received.isoformat(),
                    quality="good",
                    clock_quality=reg.clock_quality,
                    calibration_status=reg.calibration_status,
                )
                enqueue(
                    c,
                    env.message_id,
                    "inspection",
                    {
                        "sha256": env.artifact_sha256,
                        "received": received.isoformat(),
                        "mode": env.mode,
                        "replay_rate": env.replay_rate,
                        "replay_source_anchor_at": env.replay_source_anchor_at.isoformat()
                        if env.replay_source_anchor_at
                        else None,
                        "effective_acquired_at": env.replay_acquired_at.isoformat()
                        if env.replay_acquired_at
                        else None,
                        "clock_quality": reg.clock_quality,
                    },
                )
            health["last_sequence"] = max(env.sequence, prior_seq or 0)
            put(c, "source_health", env.source_id, health)
            audit(
                c,
                "accepted",
                message_id=env.message_id,
                source=env.source_id,
                received=received.isoformat(),
            )
            emit(c, "ingest", {"message_id": env.message_id, "source": env.source_id})
        committed = now()
        if env.kind == "observation":
            # Supplemental timing, after the atomic inbox/observation/job commit. It is
            # an observed upper bound, not a timestamp invented inside the transaction.
            try:
                with db.begin() as c:
                    c.execute(
                        observations.update()
                        .where(observations.c.id == obs.observation_id)
                        .values(
                            metadata={**meta, "ingest_commit_confirmed_at": committed.isoformat()}
                        )
                    )
            except Exception:
                pass  # Committed scientific effects remain valid; absent metric is censored.
        return {"status": "accepted", "id": env.message_id}
    except Exception as exc:
        with db.begin() as c:
            audit(
                c,
                "quarantined",
                digest=digest,
                error=str(exc)[:1000],
                identity=authenticated_identity,
                topic=received_topic,
                bytes=len(raw),
            )
        return {"status": "quarantined", "reason": str(exc)}
