"""One isolated, bounded controller: durable commands -> public MQTT observations."""

import ctypes
import importlib
import logging
import multiprocessing
import os
from pathlib import Path
import signal
import sys
import time
import uuid
from sqlalchemy import select, func
from twinguard.edge.contracts import now
from twinguard.edge.demo_sessions import sessions, fetch, update, enabled, CATALOG
from twinguard.edge.storage import engine, jobs

ROOT = Path(os.environ.get("TWINGUARD_ROOT", Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(ROOT))
edge_demo = importlib.import_module("scripts.edge_demo")

LOG = logging.getLogger(__name__)


def generate_child(path, seed, kind, fidelity, inspections, parent):
    # Linux parent-death signal plus bounded container prevents orphan generators.
    if sys.platform == "linux":
        ctypes.CDLL(None).prctl(1, signal.SIGTERM)
        if os.getppid() != parent:
            return
    edge_demo.generate(Path(path), seed, kind, fidelity, include_inspections=inspections)


class Hooks:
    def __init__(self, db, ident):
        self.db, self.ident = db, ident
        self.last_check = 0.0
        self.desired = "running"
        self.backlog = 0
        self.waiting = False
        self.last_heartbeat = 0.0

    def control(self):
        if time.monotonic() - self.last_check > 0.15:
            with self.db.connect() as c:
                body = fetch(c, self.ident)
                self.desired = body["desired_state"]
                self.backlog = c.execute(
                    select(func.count())
                    .select_from(jobs)
                    .where(jobs.c.status.in_(["pending", "processing"]))
                ).scalar_one()
            self.last_check = time.monotonic()
        if time.monotonic() - self.last_heartbeat > 2:
            update(self.db, self.ident, heartbeat_at=now().isoformat())
            self.last_heartbeat = time.monotonic()
        if self.desired == "running" and self.backlog > 500:
            if not self.waiting:
                update(self.db, self.ident, publisher_active=False, phase="processing_backpressure")
                self.waiting = True
            return "waiting"
        if self.waiting:
            self.waiting = False
            update(
                self.db, self.ident, publisher_active=self.desired == "running", phase="publishing"
            )
        return self.desired

    def state(self, value):
        changes = dict(
            state=value, publisher_active=value == "running", heartbeat_at=now().isoformat()
        )
        changes["paused_at" if value == "paused" else "resumed_at"] = now().isoformat()
        update(self.db, self.ident, **changes)

    def ready(self, total, source, wall):
        update(
            self.db,
            self.ident,
            state="running",
            publisher_active=True,
            total_observations=total,
            source_begin=source.isoformat(),
            replay_wall_begin=wall.isoformat(),
            phase="publishing",
        )

    def clock(self, wall_begin, pause_s):
        with self.db.connect() as c:
            body = fetch(c, self.ident)
        update(
            self.db,
            self.ident,
            replay_wall_begin=wall_begin.isoformat(),
            paused_wall_s=body.get("paused_wall_s", 0) + pause_s,
        )

    def published(self, count, record, delivery, position):
        update(
            self.db,
            self.ident,
            published_observations=count,
            playback_position_s=position,
            last_published_observation=record.observation_id,
            last_delivery=delivery,
            heartbeat_at=now().isoformat(),
            processing_backlog_at_publish=self.backlog,
        )

    def inspection(self, message_id, count):
        update(
            self.db,
            self.ident,
            published_observations=count,
            inspection_message_id=message_id,
            phase="inspection_submitted",
        )


def recover(db):
    with db.connect() as c:
        rows = list(
            c.execute(
                select(sessions.c.body).where(sessions.c.active_namespace == "default")
            ).scalars()
        )
    for body in rows:
        if body.get("controller_id"):
            update(
                db,
                body["id"],
                state="failed",
                desired_state="stopped",
                publisher_active=False,
                ended_at=now().isoformat(),
                error="Controller interrupted. Last acknowledged progress retained; an in-flight delivery may have committed. Restart creates a fresh session; no automatic dataset replay.",
            )


def run_session(db, body, instance):
    ident = body["id"]
    config = body["configuration"]
    data = Path(os.environ.get("TWINGUARD_DEMO_DATA", "/demo-data")) / ident
    data.parent.mkdir(parents=True, exist_ok=True)
    if data.exists():
        update(
            db,
            ident,
            state="failed",
            desired_state="stopped",
            error="Existing dataset requires explicit fresh session",
            ended_at=now().isoformat(),
            publisher_active=False,
        )
        return
    hooks = Hooks(db, ident)
    update(
        db,
        ident,
        controller_id=instance,
        phase="generating",
        preparation_started_at=now().isoformat(),
    )
    kind = next(item["kind"] for item in CATALOG if item["id"] == config["scenario"])
    child = multiprocessing.get_context("spawn").Process(
        target=generate_child,
        args=(
            str(data),
            config["seed"],
            kind,
            config["fidelity"],
            config["inspections"],
            os.getpid(),
        ),
        daemon=True,
    )
    child.start()
    try:
        deadline = time.monotonic() + 180
        while child.is_alive():
            if hooks.control() == "stopped":
                raise edge_demo.ReplayStopped()
            if time.monotonic() > deadline:
                raise TimeoutError("Preparation exceeded bounded duration")
            child.join(0.15)
        if child.exitcode != 0:
            raise RuntimeError("Scenario generation failed")
        if sum(p.stat().st_size for p in data.rglob("*") if p.is_file()) > 512 * 1024**2:
            raise RuntimeError("Dataset exceeds bounded size")
        update(db, ident, state="ready", phase="ready")
        if hooks.control() == "stopped":
            raise edge_demo.ReplayStopped()
        edge_demo.stream(
            data,
            data.parent / (ident + "-publisher"),
            url=os.environ.get("TWINGUARD_DEMO_API", "http://api:8000"),
            host=os.environ.get("TWINGUARD_MQTT_HOST", "broker"),
            port=int(os.environ.get("TWINGUARD_MQTT_PORT", "1883")),
            speed=config["speed"],
            inspections=config["inspections"],
            limit=80 if config["scenario"] == "interruption" else None,
            hooks=hooks,
            secrets_file=os.environ.get("TWINGUARD_DEMO_SECRETS", "/run/secrets/controller.json"),
            session_id=ident,
        )
        if config["scenario"] == "interruption":
            update(
                db,
                ident,
                publisher_active=False,
                phase="source_interruption",
                interruption_wall_s=16,
            )
            deadline = time.monotonic() + 16
            while time.monotonic() < deadline:
                if hooks.control() == "stopped":
                    raise edge_demo.ReplayStopped()
                if hooks.control() == "paused":
                    hooks.state("paused")
                    began = time.monotonic()
                    while hooks.control() == "paused":
                        time.sleep(0.1)
                    deadline += time.monotonic() - began
                    if hooks.control() == "stopped":
                        raise edge_demo.ReplayStopped()
                    hooks.state("running")
                    update(db, ident, publisher_active=False, phase="source_interruption")
                time.sleep(0.1)
        update(
            db,
            ident,
            state="completed",
            desired_state="stopped",
            publisher_active=False,
            phase="completed",
            ended_at=now().isoformat(),
        )
    except edge_demo.ReplayStopped:
        update(
            db,
            ident,
            state="stopped",
            desired_state="stopped",
            publisher_active=False,
            ended_at=now().isoformat(),
        )
    except Exception:
        LOG.exception("Simulation session failed")
        update(
            db,
            ident,
            state="failed",
            desired_state="stopped",
            publisher_active=False,
            ended_at=now().isoformat(),
            error="Simulation controller failed. Previously committed observations remain. Consult authorized controller logs.",
        )
    finally:
        if child.is_alive():
            child.terminate()
            child.join(5)
            if child.is_alive():
                child.kill()
                child.join()


def main():
    if not enabled():
        raise SystemExit("Simulation controller requires explicitly enabled simulation profile")
    db = engine(os.environ.get("TWINGUARD_DEMO_DB"))
    lock = db.connect()
    if lock.dialect.name == "postgresql":
        if not lock.execute(select(func.pg_try_advisory_lock(777470))).scalar_one():
            raise SystemExit("Another controller owns the demo namespace")
        lock.commit()
    recover(db)
    instance = uuid.uuid4().hex
    try:
        while True:
            with db.connect() as c:
                body = c.execute(
                    select(sessions.c.body).where(sessions.c.active_namespace == "default")
                ).scalar_one_or_none()
            if body:
                run_session(db, body, instance)
            time.sleep(0.25)
    finally:
        lock.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
