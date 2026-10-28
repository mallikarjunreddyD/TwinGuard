"""Dedicated leased planning jobs. No F1 lock, process control or flight endpoints."""

import io
import json
import os
from pathlib import Path
import time
import uuid
from sqlalchemy import select, text
from twinguard.inspection.contracts import InspectionPlanningRequest, PlanningSnapshot
from twinguard.inspection.observations import fingerprint, load_config, snapshot as public_states
from .storage import records, jobs, get, put, claim, enqueue, emit, audit, engine
from .contracts import now
from .artifacts import ArtifactStore

ROOT = Path(os.environ.get("TWINGUARD_ROOT", Path(__file__).resolve().parents[3]))


def store():
    return ArtifactStore(os.environ.get("TWINGUARD_ARTIFACTS", "/tmp/twinguard-artifacts"))


def get_plan(c, ident):
    row = get(c, "inspection_plan", ident)
    if not row:
        return None
    payload = store().path(row["sha256"]).read_bytes()
    import hashlib

    if hashlib.sha256(payload).hexdigest() != row["sha256"]:
        raise ValueError("Corrupt plan artifact")
    return json.loads(payload)


def submit(db, request, actor):
    config = load_config(ROOT / "configs/inspection/planner.yaml")
    digest = fingerprint(request)
    with db.begin() as c:
        # Serialize only planning submissions: protects same-ID immutability and queue bound.
        # The fast IoT worker does not acquire this advisory lock.
        if c.dialect.name == "postgresql":
            c.execute(text("SELECT pg_advisory_xact_lock(7726001)"))
        existing = get(c, "planning_request", request.request_id, lock=True)
        if existing:
            if existing["request_hash"] != digest:
                raise ValueError("Conflicting duplicate request ID")
            return existing
        if (
            c.execute(
                select(jobs.c.id).where(
                    jobs.c.kind == "planning", jobs.c.status.in_(["pending", "processing"])
                )
            )
            .fetchmany(9)
            .__len__()
            >= 8
        ):
            raise ValueError("Planning queue capacity reached")
        rows = c.execute(
            select(records.c.kind, records.c.id, records.c.body).where(
                records.c.kind.in_(["asset", "condition"])
                | (
                    (records.c.kind == "event")
                    & records.c.body["lifecycle"].as_string().not_in(["resolved", "candidate"])
                )
            )
        ).all()
        assets = [r.id for r in rows if r.kind == "asset"]
        at = now()
        states = public_states(
            at,
            assets,
            {r.id: r.body for r in rows if r.kind == "condition"},
            [r.body for r in rows if r.kind == "event"],
        )
        # Bound public history work; retain the full scientific archive outside this snapshot.
        coverage = list(
            c.execute(
                select(records.c.body)
                .where(records.c.kind == "surface_coverage")
                .order_by(records.c.at.desc())
                .limit(256)
            ).scalars()
        )
        previous = get_plan(c, request.previous_plan_id) if request.previous_plan_id else None
        if request.previous_plan_id and not previous:
            raise ValueError("Previous plan missing")
        lineage = set()
        current = previous
        for _ in range(12):
            if not current or current["plan_id"] in lineage:
                break
            lineage.add(current["plan_id"])
            current = (
                get_plan(c, current["previous_plan_id"])
                if current.get("previous_plan_id")
                else None
            )
        links = list(
            c.execute(
                select(records.c.body)
                .where(records.c.kind == "planning_simulation")
                .order_by(records.c.at.desc())
                .limit(256)
            ).scalars()
        )
        completed = [v for v in links if v["binding"]["plan_id"] in lineage]
        # A proposed view is never counted as an acquired view without a completed linked result.
        attempted = sorted({v["binding"]["viewpoint_id"] for v in completed})
        checkpoint = get(c, "checkpoint", "F1") or {}
        evidence = list(checkpoint.get("evidence", {}).values())
        for state in states:
            state.reinspection = any(
                v.get("asset_id") == state.asset_id and v.get("reinspection_candidate", False)
                for v in evidence
            )
            state.unsuccessful_attempts = sum(
                any(
                    g.get("asset_statuses", {}).get(state.asset_id) not in (None, "valid")
                    for g in link["inspection"].get("geometric", [])
                )
                for link in completed
            )
        support_row = c.execute(
            select(records.c.body)
            .where(records.c.kind == "inspection")
            .order_by(records.c.at.desc())
            .limit(1)
        ).scalar_one_or_none()
        baseline_support = (support_row or {}).get("baseline_support")
        snap = PlanningSnapshot(
            snapshot_id="snapshot-" + request.request_id,
            at=at,
            reference_hash=config.reference_sha256,
            assets=states,
            coverage=coverage,
            input_refs=["condition:" + r.id for r in rows if r.kind == "condition"]
            + sorted({source for item in coverage for source in item.get("source_ids", [])})
            + ["evidence:" + v["evidence_id"] for v in evidence if v.get("reinspection_candidate")][
                :1000
            ],
            previous_plan_id=request.previous_plan_id,
            attempted_viewpoints=attempted,
            baseline_support=baseline_support,
        )
        view_model_path = ROOT / "configs/validation/view_calibration.json"
        model_sha256 = (
            __import__("hashlib").sha256(view_model_path.read_bytes()).hexdigest()
            if request.method == "P3v2" and view_model_path.exists()
            else None
        )
        body = {
            "request": request.model_dump(mode="json"),
            "request_hash": digest,
            "snapshot": snap.model_dump(mode="json"),
            "config": config.model_dump(mode="json"),
            "actor": actor,
            "submitted_at": at.isoformat(),
            "status": "pending",
            "view_calibration_sha256": model_sha256,
        }
        put(c, "planning_request", request.request_id, body)
        enqueue(
            c,
            "planning-" + request.request_id,
            "planning",
            {"request_id": request.request_id, "priority": 100},
        )
        audit(c, "planning_requested", request_id=request.request_id, actor=actor)
        return body


def run_one(db, owner):
    job = claim(db, "planning", owner, lease_s=300)
    if not job:
        return False
    started = time.perf_counter()
    try:
        from twinguard.inspection.coverage import ReferenceSurface
        from twinguard.inspection.candidates import generate
        from twinguard.inspection.optimizer import plan
        from twinguard.inspection.contracts import PlanningConfig
        import numpy as np

        with db.connect() as c:
            body = get(c, "planning_request", job["body"]["request_id"])
        config = PlanningConfig.model_validate(body["config"])
        snap = PlanningSnapshot.model_validate(body["snapshot"])
        request = InspectionPlanningRequest.model_validate(body["request"])
        surface = ReferenceSurface(
            ROOT / config.reference_path, config.reference_sha256, config.cell_m
        )
        candidates = generate(surface, snap, config, ROOT)
        if request.method == "P3v2":
            from twinguard.inspection.qualified_optimizer import select_plan

            model_path = ROOT / "configs/validation/view_calibration.json"
            if not model_path.exists():
                raise ValueError("Frozen P3v2 view calibration is unavailable")
            if (
                __import__("hashlib").sha256(model_path.read_bytes()).hexdigest()
                != body["view_calibration_sha256"]
            ):
                raise ValueError("Planning calibration revision changed after request freezing")
            result = select_plan(
                surface, snap, config, request, candidates, json.loads(model_path.read_text()), ROOT
            )
        else:
            result = plan(surface, snap, config, request, candidates)
        data = result.model_dump(mode="json")
        digest = store().persist(json.dumps(data, sort_keys=True, allow_nan=False).encode())
        # Large cell geometry stays in immutable artifact storage, not SQL.
        buffer = io.BytesIO()
        np.savez_compressed(
            buffer, centers_world_m=surface.centers, area_m2=surface.area, asset_ids=surface.assets
        )
        map_digest = store().persist(buffer.getvalue())
        with db.begin() as c:
            locked = (
                c.execute(select(jobs).where(jobs.c.id == job["id"]).with_for_update())
                .mappings()
                .one()
            )
            if locked["owner"] != owner or locked["status"] != "processing":
                return True
            put(
                c,
                "inspection_plan",
                result.plan_id,
                {
                    "plan_id": result.plan_id,
                    "sha256": digest,
                    "coverage_map_sha256": map_digest,
                    "request_id": request.request_id,
                    "status": result.status,
                    "at": result.at.isoformat(),
                    "steps": len(result.steps),
                    "snapshot_hash": result.snapshot_hash,
                    "policy_hash": result.policy_hash,
                    "duration_s": result.estimated_duration_s,
                },
            )
            put(
                c,
                "artifact",
                digest,
                {"sha256": digest, "media_type": "application/json", "kind": "inspection_plan"},
            )
            put(
                c,
                "artifact",
                map_digest,
                {
                    "sha256": map_digest,
                    "media_type": "application/x-npz",
                    "kind": "accepted_coverage_map",
                },
            )
            body.update(status="completed", plan_id=result.plan_id, completed_at=now().isoformat())
            put(c, "planning_request", request.request_id, body)
            c.execute(
                jobs.update()
                .where(jobs.c.id == job["id"])
                .values(status="completed", duration_s=time.perf_counter() - started, error=None)
            )
            emit(c, "inspection_plan_ready", {"plan_id": result.plan_id})
    except Exception as exc:
        with db.begin() as c:
            row = (
                c.execute(select(jobs).where(jobs.c.id == job["id"]).with_for_update())
                .mappings()
                .one()
            )
            if row["owner"] == owner and row["status"] == "processing":
                c.execute(
                    jobs.update()
                    .where(jobs.c.id == job["id"])
                    .values(
                        status="pending" if row["attempts"] < 3 else "failed", error=str(exc)[:2000]
                    )
                )
                if row["attempts"] >= 3:
                    failed = get(c, "planning_request", job["body"]["request_id"])
                    failed.update(status="failed", error=str(exc)[:2000])
                    put(c, "planning_request", job["body"]["request_id"], failed)
                audit(c, "planning_failed", job_id=job["id"], error=str(exc)[:2000])
    return True


def serve():
    db = engine()
    owner = str(uuid.uuid4())
    while True:
        if not run_one(db, owner):
            time.sleep(0.25)


if __name__ == "__main__":
    serve()
