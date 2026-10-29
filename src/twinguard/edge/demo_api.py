"""Authenticated simulation commands; privileged generation is a separate service."""

import uuid
from datetime import datetime
from .contracts import now
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select, func
from .api import user, require, db
from .demo_sessions import CATALOG, Configuration, enabled, create, command, fetch, sessions
from .storage import observations, jobs

router = APIRouter(prefix="/api/v1/demo")


def key(value):
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError):
        raise HTTPException(422, "A UUID Idempotency-Key is required") from None


def operator(actor):
    require(actor, {"operator", "admin"})
    if not enabled():
        raise HTTPException(403, "Simulation execution is disabled in this deployment")


@router.get("/scenarios")
def catalog(actor=Depends(user)):
    return {
        "enabled": enabled(),
        "can_control": actor["role"] in {"operator", "admin"},
        "scenarios": CATALOG,
        "notice": "Software Simulation — No Physical Plant Control",
    }


@router.get("/sessions")
def listing(actor=Depends(user)):
    with db().connect() as c:
        return list(
            c.execute(
                select(sessions.c.body)
                .order_by(
                    sessions.c.active_namespace.desc().nulls_last(), sessions.c.created.desc()
                )
                .limit(50)
            ).scalars()
        )


@router.post("/sessions")
def new(config: Configuration, actor=Depends(user), idempotency_key: str = Header(default="")):
    operator(actor)
    try:
        return create(db(), config, actor.get("actor", "operator"), key(idempotency_key))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/sessions/{ident}")
@router.get("/sessions/{ident}/status")
def status(ident: str, actor=Depends(user)):
    with db().connect() as c:
        body = fetch(c, ident)
        if not body:
            raise HTTPException(404, "Session not found")
        result = dict(body)
        heartbeat = body.get("heartbeat_at")
        result["controller_recent"] = bool(
            heartbeat and (now() - datetime.fromisoformat(heartbeat)).total_seconds() < 6
        )
        result["publisher_active"] = bool(
            body.get("publisher_active") and result["controller_recent"]
        )
        result["accepted_observations"] = c.execute(
            select(func.count())
            .select_from(observations)
            .where(observations.c.metadata["demo_session_id"].as_string() == ident)
        ).scalar_one()
        result["processing_backlog"] = c.execute(
            select(func.count())
            .select_from(jobs)
            .where(jobs.c.status.in_(["pending", "processing"]))
        ).scalar_one()
        if body.get("inspection_message_id"):
            result["inspection_jobs"] = [
                dict(row)
                for row in c.execute(
                    select(jobs.c.id, jobs.c.status, jobs.c.error).where(
                        jobs.c.id == body["inspection_message_id"]
                    )
                ).mappings()
            ]
        result["completed_inspections"] = sum(
            j["status"] == "completed" for j in result["inspection_jobs"]
        )
        latest = (
            c.execute(
                select(observations.c.id, observations.c.received)
                .where(observations.c.metadata["demo_session_id"].as_string() == ident)
                .order_by(observations.c.received.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        result["last_accepted_observation"] = dict(latest) if latest else None
        return result


@router.post("/sessions/{ident}/{action}")
def control(
    ident: str, action: str, actor=Depends(user), idempotency_key: str = Header(default="")
):
    operator(actor)
    if action not in {"start", "pause", "resume", "stop"}:
        raise HTTPException(404, "Unknown simulation action")
    try:
        return command(db(), ident, action, actor.get("actor", "operator"), key(idempotency_key))
    except LookupError:
        raise HTTPException(404, "Session not found") from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
