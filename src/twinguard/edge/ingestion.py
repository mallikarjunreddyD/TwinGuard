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
                    if old != obs.model_dump(mode="json"):
                        raise ValueError("conflicting_observation_identity")
                    health.update(
                        last_received=received.isoformat(),
                        quality=obs.quality,
                        clock_quality=reg.clock_quality,
                        calibration_status=reg.calibration_status,
                    )
                    put(c, "source_health", env.source_id, health)
                    audit(c, "duplicate_observation", observation_id=obs.observation_id)
                    return {"status": "duplicate", "id": obs.observation_id}
                meta = {
                    "authenticated_identity": authenticated_identity,
                    "claimed_source": env.source_id,
                    "edge_received_at": received.isoformat(),
                    "effective_acquired_at": effective.isoformat(),
                    "source_clock_claim": obs.clock_quality,
                    "trusted_clock_quality": reg.clock_quality,
                    "clock_basis": reg.clock_basis,
                    "mode": env.mode,
                    "message_id": env.message_id,
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
                enqueue(c, obs.observation_id, "iot", {"observation_id": obs.observation_id})
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
                enqueue(
                    c,
                    env.message_id,
                    "inspection",
                    {
                        "sha256": env.artifact_sha256,
                        "received": received.isoformat(),
                        "mode": env.mode,
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
