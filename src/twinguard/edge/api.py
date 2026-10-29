"""Authenticated operational REST and resumable SSE; no control endpoints."""

import asyncio
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from twinguard.fusion.models import OperatorAction
from .contracts import now, SourceRegistration
from .storage import engine, records, observations, jobs, stream, get, put, list_records, audit
from .worker import checkpoint, policy, ROOT
from .artifacts import ArtifactStore

router = APIRouter(prefix="/api/v1")


def user(authorization: str = Header(default="")):
    token = authorization.removeprefix("Bearer ")
    path = Path(os.environ.get("TWINGUARD_USERS", ".edge/users.json"))
    users = json.loads(path.read_text()) if path.exists() else {}
    actor = users.get(hashlib.sha256(token.encode()).hexdigest())
    if not actor:
        raise HTTPException(401, "Authentication required")
    return actor


def require(actor, roles):
    if actor["role"] not in roles:
        raise HTTPException(403, "Role not authorized")


def db():
    return engine()


@router.get("/sites")
def sites(actor=Depends(user)):
    p = policy()
    return [
        {
            "site_id": "plant-01",
            "name": "TwinGuard laboratory demonstrator",
            "deployment_profile": os.environ.get("TWINGUARD_PROFILE", "simulation"),
            "policy_id": p.policy_id,
            "policy_version": p.version,
            "deployment_mode": p.deployment_mode,
            "clock_policy": "Original source acquisition retained; simulation replay uses declared wall-clock mapping; processing times are actual.",
        }
    ]


@router.get("/snapshot")
def snapshot(actor=Depends(user)):
    # One SQL statement sees all current conditions and active events atomically.
    with db().connect() as c:
        rows = c.execute(
            select(records.c.kind, records.c.id, records.c.body).where(
                records.c.kind.in_(["asset", "condition"])
                | (
                    (records.c.kind == "event")
                    & records.c.body["lifecycle"].as_string().not_in(["resolved", "candidate"])
                )
            )
        ).all()
    return {
        "assets": [r.body for r in rows if r.kind == "asset"],
        "conditions": {r.id: r.body for r in rows if r.kind == "condition"},
        "events": [r.body for r in rows if r.kind == "event"],
        "observed_at": now().isoformat(),
    }


@router.get("/assets")
def assets(actor=Depends(user)):
    with db().connect() as c:
        return list_records(c, "asset", limit=100)


@router.get("/assets/{asset_id}")
def asset(asset_id: str, actor=Depends(user)):
    with db().connect() as c:
        result = get(c, "asset", asset_id)
    if not result:
        raise HTTPException(404, "Asset not found")
    return result


@router.get("/assets/{asset_id}/condition")
def condition(asset_id: str, actor=Depends(user)):
    with db().connect() as c:
        return get(c, "condition", asset_id) or {
            "asset_id": asset_id,
            "severity": "unknown",
            "reason": "No qualified assessment available",
        }


@router.get("/assets/{asset_id}/observations")
def observation_query(
    asset_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    sensor: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    demo_session: str | None = Query(default=None, max_length=80),
    actor=Depends(user),
):
    q = select(observations).where(observations.c.asset == asset_id)
    if demo_session:
        q = q.where(observations.c.metadata["demo_session_id"].as_string() == demo_session)
    if sensor:
        q = q.where(observations.c.sensor == sensor)
    if since:
        q = q.where(observations.c.acquired >= since.isoformat())
    if until:
        q = q.where(observations.c.acquired <= until.isoformat())
    with db().connect() as c:
        return [
            dict(r)
            for r in c.execute(
                q.order_by(observations.c.received.desc()).limit(limit).offset(offset)
            ).mappings()
        ]


@router.get("/assets/{asset_id}/analytics")
def analytics(asset_id: str, limit: int = Query(100, ge=1, le=500), actor=Depends(user)):
    with db().connect() as c:
        return list_records(c, "analysis", asset_id, limit)


@router.get("/assets/{asset_id}/evidence")
def evidence(asset_id: str, limit: int = Query(100, ge=1, le=1000), actor=Depends(user)):
    with db().connect() as c:
        return list_records(c, "evidence", asset_id, limit)


@router.get("/inspections")
def inspections(limit: int = Query(50, ge=1, le=100), actor=Depends(user)):
    with db().connect() as c:
        return list_records(c, "inspection", limit=limit)


@router.get("/inspections/{inspection_id}")
def inspection(inspection_id: str, actor=Depends(user)):
    with db().connect() as c:
        result = get(c, "inspection", inspection_id)
    if result is None:
        raise HTTPException(404, "Inspection not found")
    return result


@router.get("/assessments")
def assessments(
    asset_id: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    actor=Depends(user),
):
    with db().connect() as c:
        return list_records(c, "trace", asset_id, limit, offset)


@router.get("/events")
def events(
    asset_id: str | None = None,
    severity: str | None = None,
    state: str | None = None,
    hazard: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    actor=Depends(user),
):
    q = select(records.c.body).where(records.c.kind == "event")
    if asset_id:
        q = q.where(records.c.asset == asset_id)
    for key, value in [("severity", severity), ("lifecycle", state), ("hazard_id", hazard)]:
        if value:
            q = q.where(records.c.body[key].as_string() == value)
    with db().connect() as c:
        return list(
            c.execute(q.order_by(records.c.at.desc()).limit(limit).offset(offset)).scalars()
        )


@router.get("/events/{event_id}")
def event(event_id: str, actor=Depends(user)):
    with db().connect() as c:
        result = get(c, "event", event_id)
    if result is None:
        raise HTTPException(404, "Event not found")
    return result


@router.get("/events/{event_id}/history")
def event_history(event_id: str, limit: int = Query(100, ge=1, le=1000), actor=Depends(user)):
    with db().connect() as c:
        q = (
            select(records.c.body)
            .where(records.c.kind == "notice", records.c.body["event_id"].as_string() == event_id)
            .order_by(records.c.at)
            .limit(limit)
        )
        return list(c.execute(q).scalars())


@router.get("/events/{event_id}/actions")
def event_actions(event_id: str, actor=Depends(user)):
    with db().connect() as c:
        return list(
            c.execute(
                select(records.c.body)
                .where(
                    records.c.kind == "operator_action",
                    records.c.body["target_event"].as_string() == event_id,
                )
                .order_by(records.c.at)
                .limit(100)
            ).scalars()
        )


class ActionBody(BaseModel):
    rationale: str = Field(min_length=3, max_length=1000)


@router.post("/events/{event_id}/acknowledge")
def acknowledge(event_id: str, body: ActionBody, actor=Depends(user)):
    require(actor, ["operator", "admin"])
    with db().begin() as c:
        target = get(c, "event", event_id)
        if target is None:
            raise HTTPException(404, "Event not found")
        ident = "ack-" + hashlib.sha256((event_id + actor["actor"]).encode()).hexdigest()[:24]
        existing = get(c, "operator_action", ident)
        if existing:
            return existing
        action = OperatorAction(
            action_id=ident,
            asset_id=target["asset_id"],
            hazard_id=target["hazard_id"],
            at=now(),
            kind="acknowledge",
            rationale=body.rationale,
        )
        checkpoint(c, [], [action])
        result = {
            **action.model_dump(mode="json"),
            "actor": actor["actor"],
            "target_event": event_id,
        }
        put(c, "operator_action", ident, result, target["asset_id"])
        audit(c, "operator_acknowledge", **result)
        return result


@router.post("/sources")
def register(source: SourceRegistration, actor=Depends(user)):
    require(actor, ["admin"])
    if source.calibration_status == "verified" or source.clock_quality == "synchronized":
        raise HTTPException(
            422,
            "Verified calibration/clock require reviewed offline configuration; browser cannot grant trust",
        )
    with db().begin() as c:
        put(c, "source", source.source_id, source.model_dump(mode="json"))
        audit(c, "source_registration", actor=actor["actor"], source=source.source_id)
    return source


@router.post("/inspection-imports")
async def import_bundle(request: Request, actor=Depends(user)):
    require(actor, ["operator", "admin"])
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 64 * 1024 * 1024:
            raise HTTPException(413, "Artifact size limit")
        chunks.append(chunk)
    try:
        store = ArtifactStore(os.environ.get("TWINGUARD_ARTIFACTS", "/tmp/twinguard-artifacts"))
        digest = await asyncio.to_thread(store.upload, b"".join(chunks))
    except Exception as exc:
        with db().begin() as c:
            audit(c, "artifact_rejected", actor=actor["actor"], error=str(exc)[:500])
        raise HTTPException(422, str(exc)) from exc
    with db().begin() as c:
        put(c, "artifact", digest, {"sha256": digest, "size": size, "actor": actor["actor"]})
        audit(c, "artifact_uploaded", sha256=digest, actor=actor["actor"])
    return {
        "sha256": digest,
        "status": "verified; publish authorized manifest to schedule processing",
    }


@router.get("/artifacts/{digest}")
def artifact_file(digest: str, actor=Depends(user)):
    with db().connect() as c:
        entry = get(c, "artifact", digest)
    if not entry:
        raise HTTPException(404, "No public artifact")
    store = ArtifactStore(os.environ.get("TWINGUARD_ARTIFACTS", "/tmp/twinguard-artifacts"))
    return FileResponse(store.path(digest), media_type=entry.get("media_type", "application/zip"))


@router.get("/model")
def model(actor=Depends(user)):
    return FileResponse(ROOT / "configs/edge/plant.glb", media_type="model/gltf-binary")


@router.get("/monitoring/health")
def monitoring(actor=Depends(user)):
    result = []
    with db().connect() as c:
        for reg in list_records(c, "source", limit=1000):
            health = get(c, "source_health", reg["source_id"]) or {}
            age = (
                (now() - datetime.fromisoformat(health["last_received"])).total_seconds()
                if health.get("last_received")
                else None
            )
            channels = []
            for sensor, mapping in reg["sensors"].items():
                sample = (
                    c.execute(
                        select(observations)
                        .where(observations.c.sensor == sensor)
                        .order_by(observations.c.received.desc())
                        .limit(1)
                    )
                    .mappings()
                    .first()
                )
                channel_age = (
                    (now() - datetime.fromisoformat(sample["received"])).total_seconds()
                    if sample
                    else None
                )
                channels.append(
                    {
                        "sensor_id": sensor,
                        **mapping,
                        "last_received": sample["received"] if sample else None,
                        "last_valid": sample["received"]
                        if sample
                        and sample["body"]["quality"] == "good"
                        and reg["calibration_status"] != "unknown"
                        else None,
                        "quality": sample["body"]["quality"] if sample else "missing",
                        "stale": channel_age is None
                        or channel_age > reg["expected_interval_s"] * 3,
                        "clock_quality": reg["clock_quality"],
                        "calibration_status": reg["calibration_status"],
                    }
                )
            result.append(
                {
                    **reg,
                    **health,
                    "channels": channels,
                    "age_s": age,
                    "connection": "connected"
                    if age is not None and age < reg["expected_interval_s"] * 3
                    else "no_recent_data",
                    "monitoring_status": "available"
                    if age is not None
                    and age < reg["expected_interval_s"] * 3
                    and health.get("quality") == "good"
                    else "unknown_or_unavailable",
                }
            )
    return result


@router.get("/platform/health")
def platform_health(actor=Depends(user)):
    with db().connect() as c:
        counts = dict(c.execute(select(jobs.c.status, func.count()).group_by(jobs.c.status)).all())
        worker = get(c, "service", "fast-worker")
        committed = c.execute(select(func.count()).select_from(observations)).scalar_one()
    return {
        "database": "connected",
        "jobs": counts,
        "worker": worker,
        "observations": committed,
        "readiness": "ready"
        if worker and (now() - datetime.fromisoformat(worker["heartbeat"])).total_seconds() < 15
        else "worker_unavailable",
        "policy": policy().model_dump(mode="json"),
        "profile": os.environ.get("TWINGUARD_PROFILE", "simulation"),
    }


@router.get("/stream")
async def events_stream(
    request: Request,
    after: int = Query(0, ge=0),
    last_event_id: str | None = Header(None),
    actor=Depends(user),
):
    try:
        cursor = max(after, int(last_event_id or 0))
    except ValueError as exc:
        raise HTTPException(422, "Invalid stream cursor") from exc

    async def generate():
        nonlocal cursor
        while not await request.is_disconnected():
            with db().connect() as c:
                rows = (
                    c.execute(
                        select(stream)
                        .where(stream.c.seq > cursor)
                        .order_by(stream.c.seq)
                        .limit(100)
                    )
                    .mappings()
                    .all()
                )
            for row in rows:
                cursor = row["seq"]
                yield f"id: {cursor}\ndata: {json.dumps(dict(row))}\n\n"
            if not rows:
                yield ": keepalive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
