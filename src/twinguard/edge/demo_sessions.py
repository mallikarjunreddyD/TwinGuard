"""Public bounded demo contracts and durable lifecycle; no simulator imports."""

import os
import uuid
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import MetaData, Table, Column, String, JSON, select, func
from .contracts import now

meta = MetaData()
sessions = Table(
    "demo_sessions",
    meta,
    Column("id", String(80), primary_key=True),
    Column("active_namespace", String(80), unique=True),
    Column("created", String(40), nullable=False),
    Column("body", JSON, nullable=False),
)
commands = Table(
    "demo_commands",
    meta,
    Column("id", String(160), primary_key=True),
    Column("session_id", String(80), nullable=False, index=True),
    Column("action", String(20), nullable=False),
    Column("created", String(40), nullable=False),
)

CATALOG = [
    dict(
        id="healthy",
        name="Healthy Operation",
        description="Synthetic process sensors under ordinary operation. Qualified monitoring depends on calibration and coverage; no whole-plant green guarantee.",
        kind="healthy",
        inspections=True,
    ),
    dict(
        id="geometry",
        name="Localized Deformation",
        description="Original virtual LiDAR and B3.1 processing of a localized scenario. Detection is not guaranteed, especially with L2 sensing.",
        kind="geometry",
        inspections=True,
    ),
    dict(
        id="thermal",
        name="Thermal Anomaly",
        description="Virtual radiometric inspection and operating analytics. Image findings do not imply verified 3D association.",
        kind="thermal",
        inspections=True,
    ),
    dict(
        id="critical",
        name="Critical Pressure",
        description="Synthetic pressure exceeds illustrative limits. Existing F1 evaluates critical evidence without UAV corroboration; service delays can still make it stale.",
        kind="critical",
        inspections=False,
    ),
    dict(
        id="degraded",
        name="Degraded Sensing",
        description="L2 LiDAR observing a localized scenario; demonstrates unsupported measurements and possible inconclusive geometry.",
        kind="geometry",
        inspections=True,
    ),
    dict(
        id="interruption",
        name="Sensor Interruption",
        description="Healthy IoT replay followed by 16 seconds without publication. Existing monitoring observes missing input; stored measurements remain.",
        kind="healthy",
        inspections=False,
    ),
]


class Configuration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: Literal["healthy", "geometry", "thermal", "critical", "degraded", "interruption"] = (
        "healthy"
    )
    fidelity: Literal["L1", "L2"] = "L1"
    speed: Literal[1, 2, 5, 10] = 2
    inspections: bool = True
    seed: int = Field(default=21000, ge=20000, le=999999)


def enabled():
    return (
        os.environ.get("TWINGUARD_PROFILE", "") == "simulation"
        and os.environ.get("TWINGUARD_DEMO_ENABLED", "0") == "1"
    )


def fetch(c, ident, lock=False):
    q = select(sessions.c.body).where(sessions.c.id == ident)
    if lock:
        q = q.with_for_update()
    return c.execute(q).scalar_one_or_none()


def save(c, body, active=None):
    values = dict(body=body)
    if active is not None:
        values["active_namespace"] = "default" if active else None
    c.execute(sessions.update().where(sessions.c.id == body["id"]).values(**values))


def create(db, config, actor, key):
    ident = "demo-" + uuid.uuid5(uuid.NAMESPACE_URL, actor + ":" + key).hex
    values = config.model_dump()
    if values["scenario"] == "degraded":
        values["fidelity"] = "L2"
    if values["scenario"] in {"critical", "interruption"}:
        values["inspections"] = False
    body = dict(
        id=ident,
        configuration_version="demo-v1",
        configuration=values,
        actor=actor,
        created_at=now().isoformat(),
        state="idle",
        desired_state="idle",
        published_observations=0,
        total_observations=None,
        playback_position_s=0,
        publisher_active=False,
        inspection_jobs=[],
        error=None,
        provenance=dict(mode="software_simulation", no_physical_control=True, dataset_id=ident),
        history=[],
    )
    with db.begin() as c:
        if c.dialect.name == "postgresql":
            c.execute(select(func.pg_advisory_xact_lock(777471)))
        old = fetch(c, ident)
        if old:
            if old["configuration"] != values:
                raise ValueError("Idempotency key already used with different configuration")
            return old
        if c.execute(select(func.count()).select_from(sessions)).scalar_one() >= 200:
            raise ValueError("Demo session capacity reached; administrator storage review required")
        c.execute(sessions.insert().values(id=ident, created=body["created_at"], body=body))
    return body


def command(db, ident, action, actor, key):
    with db.begin() as c:
        if c.dialect.name == "postgresql":
            c.execute(select(func.pg_advisory_xact_lock(777471)))
        body = fetch(c, ident, True)
        if not body:
            raise LookupError("Session not found")
        command_id = ident + ":" + key
        old = c.execute(select(commands).where(commands.c.id == command_id)).mappings().first()
        if old:
            if old["action"] != action:
                raise ValueError("Command key already used for another action")
            return body
        state = body["state"]
        allowed = {
            "start": {"idle", "ready"},
            "pause": {"running"},
            "resume": {"paused"},
            "stop": {"preparing", "ready", "running", "paused", "stopping"},
        }
        # Repeated Start with a different request key cannot create another publisher.
        if action == "start" and state in {"preparing", "running", "paused"}:
            return body
        if action not in allowed or state not in allowed[action]:
            raise ValueError("Invalid simulation lifecycle transition")
        if action == "start":
            busy = c.execute(
                select(sessions.c.id).where(sessions.c.active_namespace == "default")
            ).scalar_one_or_none()
            if busy and busy != ident:
                raise ValueError("Another session owns the demo namespace")
            body.update(state="preparing", desired_state="running", started_at=now().isoformat())
        elif action == "stop":
            body.update(desired_state="stopped", state="stopping")
        else:
            body["desired_state"] = "paused" if action == "pause" else "running"
        body["history"].append(dict(action=action, actor=actor, at=now().isoformat()))
        save(c, body, active=True)
        c.execute(
            commands.insert().values(
                id=command_id, session_id=ident, action=action, created=now().isoformat()
            )
        )
        return body


def update(db, ident, **changes):
    with db.begin() as c:
        body = fetch(c, ident, True)
        if not body:
            raise LookupError("Session not found")
        body.update(changes)
        save(c, body, active=False if body["state"] in {"completed", "stopped", "failed"} else None)
        return body
