"""Restart-safe jobs invoking unchanged public analytics and Phase 4 F1."""

import json
from functools import lru_cache
import os
import time
import uuid
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from sqlalchemy import select
from twinguard.core.contracts import SensorObservation, InspectionCapture
from twinguard.core.observations import load_capture_arrays
from twinguard.analytics.config import AnalyticsConfig
from twinguard.analytics.reference import load_reference
from twinguard.analytics.operating import infer_operating
from twinguard.fusion import adapters
from twinguard.fusion.engine import assess
from twinguard.fusion.models import FusionState, ProcessingRecord
from twinguard.fusion.policies import load_policy, policy_hash
from .contracts import now
from .storage import engine, get, put, emit, audit, observations, jobs, claim
from .artifacts import ArtifactStore

ROOT = Path(os.environ.get("TWINGUARD_ROOT", ".")).resolve()


@lru_cache(maxsize=8)
def _validated_policy(path, mtime_ns, size):
    return load_policy(Path(path))


def policy():
    profile = os.environ.get("TWINGUARD_PROFILE", "simulation")
    if profile not in ["simulation", "site-review"]:
        raise ValueError("Unknown deployment profile")
    path = ROOT / (
        "configs/fusion/hazards.yaml"
        if profile == "simulation"
        else "configs/fusion/site-template.yaml"
    )
    revision = path.stat()
    return _validated_policy(str(path), revision.st_mtime_ns, revision.st_size)


def processing(source, received, clock):
    done = now()
    return ProcessingRecord(
        source_id=source,
        received_at=received,
        processed_at=done,
        available_at=done,
        basis="recorded",
        clock_quality=clock,
        rationale="Actual edge worker wall-clock completion; original acquisition retained in durable observation. Explicit controlled replay acquisition mapping where configured.",
    )


def checkpoint(c, evidence, actions=()):
    p = policy()
    # All fusion transitions serialize on one locked state row, in the commit transaction.
    raw = get(c, "checkpoint", "F1", lock=True)
    if raw is None:
        raise RuntimeError("Initialize durable checkpoint before workers start")
    state = FusionState.model_validate(raw)
    began = now()
    state, history = assess(state, evidence, p, began, actions=actions)
    # Durable evidence rows retain full history; the operational working set preserves
    # every live horizon, latest stream sample and all unresolved-event support.
    protected = {
        key
        for event in state.events.values()
        if event.lifecycle != "resolved"
        for key in event.positive_ids + event.recovery_ids
    }
    latest = {}
    for e in state.evidence.values():
        key = (e.sensor_id, e.hypothesis, e.asset_id, e.scope, e.algorithm)
        if key not in latest or e.acquired_at > latest[key].acquired_at:
            latest[key] = e
    protected.update(e.evidence_id for e in latest.values())
    horizons = {
        m: max([r.max_age_s for r in p.rules if m in r.modalities] + [0])
        for m in ["fixed_sensor", "geometric", "thermal"]
    }
    state.evidence = {
        key: e
        for key, e in state.evidence.items()
        if key in protected
        or (began - e.acquired_at).total_seconds()
        <= horizons[e.modality] + p.max_clock_uncertainty_s
    }
    put(c, "checkpoint", "F1", state.model_dump(mode="json"))
    for e in evidence:
        put(c, "evidence", e.evidence_id, e.model_dump(mode="json"), e.asset_id)
    for trace in history:
        data = trace.model_dump(mode="json")
        data["deployment_profile"] = os.environ.get("TWINGUARD_PROFILE", "simulation")
        put(c, "trace", trace.assessment.assessment_id, data, trace.assessment.asset_id)
        put(c, "condition", trace.assessment.asset_id, data, trace.assessment.asset_id)
    for event in state.events.values():
        put(
            c,
            "event",
            event.event_id,
            {
                **event.model_dump(mode="json"),
                "policy_id": p.policy_id,
                "policy_version": p.version,
                "policy_sha256": policy_hash(p),
                "deployment_profile": os.environ.get("TWINGUARD_PROFILE", "simulation"),
            },
            event.asset_id,
        )
    for notice in state.notices:
        put(c, "notice", notice.notice_id, notice.model_dump(mode="json"))
    emit(
        c,
        "assessment",
        {
            "assets": [h.assessment.asset_id for h in history],
            "fusion_started_at": began.isoformat(),
            "available_at": now().isoformat(),
            "policy_hash": policy_hash(p),
            "profile": os.environ.get("TWINGUARD_PROFILE", "simulation"),
        },
    )
    return history


def iot(db, job):
    with db.connect() as c:
        row = dict(
            c.execute(
                select(observations).where(observations.c.id == job["body"]["observation_id"])
            )
            .mappings()
            .one()
        )
        context = list(
            c.execute(
                select(observations.c.body)
                .where(
                    observations.c.acquired <= row["acquired"],
                    observations.c.body["provenance_id"].as_string()
                    == row["body"]["provenance_id"],
                )
                .order_by(observations.c.acquired.desc())
                .limit(500)
            ).scalars()
        )
    original = SensorObservation.model_validate(row["body"])
    meta = row["metadata"]
    effective = original.model_copy(
        update={
            "acquired_at": datetime.fromisoformat(meta["effective_acquired_at"]),
            "received_at": datetime.fromisoformat(row["received"]),
            "clock_quality": meta["trusted_clock_quality"],
        }
    )
    # Trust comes from registry; unknown calibration cannot use synthetic authority assumptions.
    if meta["calibration_status"] not in (
        ["assumed_simulation", "verified"]
        if os.environ.get("TWINGUARD_PROFILE", "simulation") == "simulation"
        else ["verified"]
    ):
        effective = effective.model_copy(update={"quality": "unknown"})
    evidence = []
    raw = adapters.engineering_limit(
        effective,
        processing(original.observation_id, effective.received_at, effective.clock_quality),
        policy(),
    )
    if raw:
        evidence.append(raw)
    model = json.loads((ROOT / "configs/fusion/calibration/operating_model.json").read_text())
    predictions = infer_operating(
        [SensorObservation.model_validate(r) for r in context], model, AnalyticsConfig()
    )
    prediction = next((p for p in predictions if p.observation_id == original.observation_id), None)
    if prediction:
        # Scientific inference retains original times/context; only delivery availability and declared replay clock map to edge time.
        evidence.append(
            adapters.operating(
                prediction,
                original.model_copy(update={"quality": effective.quality}),
                processing(
                    prediction.prediction_id, effective.received_at, effective.clock_quality
                ),
            ).model_copy(update={"acquired_at": effective.acquired_at})
        )
    return evidence, {
        "operating": prediction.model_dump(mode="json") if prediction else None,
        "original_acquired_at": original.acquired_at.isoformat(),
        "asset_id": original.asset_id,
    }


def mapped_capture_time(acquired_at, data):
    if data["mode"] != "simulation_replay":
        return acquired_at
    mapped = datetime.fromisoformat(data["effective_acquired_at"])
    anchor = datetime.fromisoformat(data["replay_source_anchor_at"])
    return mapped - timedelta(seconds=(anchor - acquired_at).total_seconds() / data["replay_rate"])


def inspection(db, job):
    from twinguard.analytics.pipeline import analyze_geometry
    from twinguard.analytics.thermal import infer_thermal

    data = job["body"]
    received = datetime.fromisoformat(data["received"])
    store = ArtifactStore(os.environ.get("TWINGUARD_ARTIFACTS", "/tmp/twinguard-artifacts"))
    evidence = []
    output = {"geometric": [], "thermal": [], "thermal_images": [], "asset_id": "BW-01"}
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        records = store.extract(data["sha256"], root)
        captures = [r for r in records if isinstance(r, InspectionCapture)]
        config = AnalyticsConfig()
        ref = load_reference(ROOT / "configs/analytics/accepted_reference.json")
        lidar = sorted([r for r in captures if r.modality == "lidar"], key=lambda r: r.acquired_at)
        if len(lidar) >= 2:
            calibration = json.loads(
                (ROOT / "configs/fusion/calibration/geometry_b31.json").read_text()
            )
            geometry_method = os.environ.get("TWINGUARD_GEOMETRY_METHOD", "B3.1")
            if geometry_method not in ("B3.1", "B3.2"):
                raise ValueError("Unsupported geometry method")
            view_model = (
                json.loads((ROOT / "configs/validation/view_calibration.json").read_text())
                if geometry_method == "B3.2"
                else None
            )
            r, g = analyze_geometry(
                root / lidar[0].artifact.uri,
                root / lidar[-1].artifact.uri,
                config,
                ref,
                root / "derived",
                methods=[geometry_method],
                improved_calibration=calibration,
                view_calibration=view_model,
            )[geometry_method]
            evidence.extend(
                adapters.geometry(
                    g,
                    r,
                    processing(g.analysis_id, received, data["clock_quality"]),
                    lidar[-1].provenance_id,
                )
            )
            output["geometric"] = [g.model_dump(mode="json")]
            registered = (root / "derived" / r.registered_artifact.uri).read_bytes()
            object_hash = store.persist(registered)
            if object_hash != r.registered_artifact.sha256:
                raise ValueError("Derived registered cloud hash mismatch")
            r.registered_artifact.uri = "/api/v1/artifacts/" + object_hash
            output["derived_artifacts"] = [
                {
                    "sha256": object_hash,
                    "media_type": "application/x-npz",
                    "size": len(registered),
                    "origin": "computed_registered_measurements",
                    "capture_id": lidar[-1].capture_id,
                }
            ]
            output["registration"] = r.model_dump(mode="json")
            # Planning coverage is a downstream public-data product; it cannot alter F1 evidence.
            from twinguard.inspection.coverage import ReferenceSurface
            from twinguard.inspection.qualification import from_analytics
            from twinguard.inspection.observations import load_config as planner_config
            import io
            import numpy as np

            pc = planner_config(ROOT / "configs/inspection/planner.yaml")
            reference_surface = ReferenceSurface(
                ROOT / pc.reference_path, pc.reference_sha256, pc.cell_m
            )
            with np.load(io.BytesIO(registered), allow_pickle=False) as cloud:
                coverage_record = from_analytics(
                    reference_surface,
                    cloud["points_m"],
                    lidar[-1],
                    r,
                    g,
                    now(),
                    mapped_capture_time(lidar[-1].acquired_at, data),
                )
            output["surface_coverage"] = [coverage_record.model_dump(mode="json")]
            from twinguard.inspection.contracts import BaselineInspectionSupport

            baseline_points = load_capture_arrays(root, lidar[0])["points_m"]
            baseline_pose = np.asarray(lidar[0].sensor_pose.matrix)
            baseline_world = baseline_points @ baseline_pose[:3, :3].T + baseline_pose[:3, 3]
            output["baseline_support"] = BaselineInspectionSupport(
                capture_id=lidar[0].capture_id,
                reference_hash=reference_surface.hash,
                reported_pose=lidar[0].sensor_pose,
                acquired_at=mapped_capture_time(lidar[0].acquired_at, data),
                available_at=now(),
                acquisition_parameters={
                    k: v
                    for k, v in lidar[0].acquisition_parameters.items()
                    if isinstance(v, (float, int)) and not isinstance(v, bool)
                },
                observed_cells=reference_surface.associate(baseline_world, pc.association_m),
            ).model_dump(mode="json")

        for capture in [r for r in captures if r.modality == "thermal"]:
            result, thermal_arrays = infer_thermal(
                root, capture, ROOT / "configs/fusion/calibration", config, ref
            )
            evidence.extend(
                adapters.thermal(
                    result,
                    processing(result.analysis_id, received, data["clock_quality"]),
                    capture.provenance_id,
                )
            )
            output["thermal"].append(result.model_dump(mode="json"))
            residual = thermal_arrays["residual_c"]
            arrays = load_capture_arrays(root, capture)
            import numpy as np

            t = arrays["temperature_c"]
            output["thermal_images"].append(
                {
                    "capture_id": capture.capture_id,
                    "acquired_at": capture.acquired_at.isoformat(),
                    "temperature_c": np.where(np.isfinite(t), t, 0).tolist(),
                    "valid_mask": arrays["valid_mask"].tolist(),
                    "saturation_mask": arrays.get(
                        "saturation_mask", np.zeros(t.shape, bool)
                    ).tolist(),
                    "residual": np.where(np.isfinite(residual), residual, 0).tolist(),
                }
            )
    if data["mode"] == "simulation_replay":
        evidence = [
            e.model_copy(
                update={
                    "acquired_at": mapped_capture_time(e.acquired_at, data),
                    "reasons": e.reasons
                    + [
                        f"Controlled replay original acquisition {e.acquired_at.isoformat()}, rate {data['replay_rate']}; actual availability retained"
                    ],
                }
            )
            for e in evidence
        ]

    return evidence, output


def run_one(db, kind, owner):
    job = claim(
        db,
        kind,
        owner,
        lease_s=int(os.environ.get("TWINGUARD_JOB_LEASE_S", "15" if kind == "iot" else "120")),
    )
    if job is None:
        return False
    started = now()
    try:
        evidence, result = iot(db, job) if kind == "iot" else inspection(db, job)
        analytics_done = now()
        with db.begin() as c:
            locked = (
                c.execute(select(jobs).where(jobs.c.id == job["id"]).with_for_update())
                .mappings()
                .one()
            )
            if locked["owner"] != owner or locked["status"] != "processing":
                return True
            history = checkpoint(c, evidence)
            finished = now()
            result.update(
                job_id=job["id"],
                kind=kind,
                started_at=started.isoformat(),
                analytics_completed_at=finished.isoformat(),
                policy_hash=policy_hash(policy()),
            )
            put(c, "analysis", job["id"], result, result.get("asset_id"))
            for artifact in result.get("derived_artifacts", []):
                put(c, "artifact", artifact["sha256"], artifact)
            for coverage_record in result.get("surface_coverage", []):
                put(
                    c,
                    "surface_coverage",
                    coverage_record["source_ids"][0],
                    coverage_record,
                    coverage_record["asset_id"],
                )
            if kind == "inspection":
                put(c, "inspection", job["id"], {**result, **job["body"]}, "BW-01")
            c.execute(
                jobs.update()
                .where(jobs.c.id == job["id"])
                .values(
                    status="completed", duration_s=(finished - started).total_seconds(), error=None
                )
            )
            put(
                c,
                "timing",
                job["id"],
                {
                    "job_id": job["id"],
                    "kind": kind,
                    "job_start": started.isoformat(),
                    "analytics_complete": analytics_done.isoformat(),
                    "advisory_available": now().isoformat(),
                    "assessments": [h.assessment.assessment_id for h in history],
                },
            )
            emit(
                c,
                "job_completed",
                {
                    "job_id": job["id"],
                    "kind": kind,
                    "assets": [h.assessment.asset_id for h in history],
                },
            )
        committed = now()
        with db.begin() as c:
            timing = get(c, "timing", job["id"])
            timing["advisory_commit_confirmed_at"] = committed.isoformat()
            put(c, "timing", job["id"], timing)
        return True
    except Exception as exc:
        with db.begin() as c:
            row = c.execute(select(jobs.c.attempts).where(jobs.c.id == job["id"])).scalar_one()
            c.execute(
                jobs.update()
                .where(jobs.c.id == job["id"])
                .values(status="pending" if row < 3 else "failed", error=str(exc)[:2000])
            )
            audit(
                c,
                "job_retry" if row < 3 else "job_quarantined",
                job_id=job["id"],
                error=str(exc)[:2000],
            )
        return True


def serve(kind):
    db = engine()
    owner = str(uuid.uuid4())
    tick = 0.0
    while True:
        busy = run_one(db, kind, owner)
        if kind == "iot" and time.monotonic() - tick > 2:
            with db.begin() as c:
                checkpoint(c, [])
                put(c, "service", "fast-worker", {"heartbeat": now().isoformat()})
            tick = time.monotonic()
        if not busy:
            time.sleep(0.1)


if __name__ == "__main__":
    import sys

    serve(sys.argv[1] if len(sys.argv) > 1 else "iot")
