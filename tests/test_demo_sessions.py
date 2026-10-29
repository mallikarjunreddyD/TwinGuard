"""Durable demo state, role/profile isolation and unchanged public transport semantics."""

from datetime import timedelta
import hashlib
import json
from pathlib import Path
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from twinguard.api.app import app
from twinguard.edge import api, demo_api
from twinguard.edge.demo_sessions import (
    Configuration,
    create,
    command,
    update,
    fetch,
    meta,
    sessions,
)
from twinguard.edge.storage import metadata, records, put, observations
from twinguard.edge.contracts import now, SourceRegistration, Envelope
from twinguard.edge.ingestion import ingest, topic
from twinguard.demo.controller import recover
from twinguard.core.contracts import SensorObservation


@pytest.fixture
def db(tmp_path, monkeypatch):
    e = create_engine("sqlite:///" + str(tmp_path / "demo.sqlite"))
    metadata.create_all(e)
    meta.create_all(e)
    monkeypatch.setenv("TWINGUARD_PROFILE", "simulation")
    monkeypatch.setenv("TWINGUARD_DEMO_ENABLED", "1")
    monkeypatch.setattr(demo_api, "db", lambda: e)
    monkeypatch.setattr(api, "db", lambda: e)
    yield e
    app.dependency_overrides.clear()
    e.dispose()


def make(db, **changes):
    return create(db, Configuration(**changes), "operator-test", str(uuid.uuid4()))


def act(db, body, action, key=None):
    return command(db, body["id"], action, "operator-test", key or str(uuid.uuid4()))


def test_catalog_and_normalization(db):
    app.dependency_overrides[api.user] = lambda: {"role": "viewer", "actor": "viewer-test"}
    c = TestClient(app)
    catalog = c.get("/api/v1/demo/scenarios").json()
    assert len(catalog["scenarios"]) == 6
    assert catalog["can_control"] is False
    assert make(db, scenario="degraded")["configuration"]["fidelity"] == "L2"
    assert make(db, scenario="critical")["configuration"]["inspections"] is False


@pytest.mark.parametrize(
    "change",
    [
        {"scenario": "shell"},
        {"speed": 20},
        {"seed": -1},
        {"path": "/etc/passwd"},
        {"fidelity": "perfect"},
    ],
)
def test_invalid_config_rejected(change):
    with pytest.raises(ValueError):
        Configuration(**change)


def test_create_start_idempotence_and_namespace(db):
    key = str(uuid.uuid4())
    a = create(db, Configuration(), "op", key)
    b = create(db, Configuration(), "op", key)
    assert a["id"] == b["id"]
    command_key = str(uuid.uuid4())
    assert act(db, a, "start", command_key)["state"] == "preparing"
    assert act(db, a, "start", command_key)["state"] == "preparing"
    assert act(db, a, "start")["state"] == "preparing"
    with db.connect() as c:
        assert c.execute(select(func.count()).select_from(sessions)).scalar_one() == 1
    with pytest.raises(ValueError, match="namespace"):
        act(db, make(db), "start")


def test_lifecycle_persistence_stop_does_not_clear_events(db):
    body = make(db)
    with db.begin() as c:
        put(c, "event", "keep-event", {"lifecycle": "active", "severity": "red"})
    act(db, body, "start")
    update(db, body["id"], state="running", published_observations=8)
    assert act(db, body, "pause")["desired_state"] == "paused"
    update(db, body["id"], state="paused")
    assert act(db, body, "resume")["desired_state"] == "running"
    update(db, body["id"], state="running")
    assert act(db, body, "stop")["state"] == "stopping"
    update(db, body["id"], state="stopped", publisher_active=False)
    with db.connect() as c:
        saved = fetch(c, body["id"])
        assert saved["published_observations"] == 8
        assert (
            c.execute(select(records.c.id).where(records.c.kind == "event")).scalar_one()
            == "keep-event"
        )
    assert act(db, make(db), "start")["state"] == "preparing"


def test_restart_is_fresh_identity_and_invalid_transition(db):
    first = make(db)
    with pytest.raises(ValueError, match="transition"):
        act(db, first, "resume")
    act(db, first, "start")
    update(db, first["id"], state="completed")
    with pytest.raises(ValueError, match="transition"):
        act(db, first, "start")
    assert make(db)["id"] != first["id"]


def test_controller_crash_preserves_cursor_without_republication(db):
    a = make(db)
    act(db, a, "start")
    update(
        db,
        a["id"],
        controller_id="old-instance",
        state="running",
        published_observations=17,
        playback_position_s=9,
    )
    recover(db)
    with db.connect() as c:
        row = fetch(c, a["id"])
    assert row["state"] == "failed"
    assert row["published_observations"] == 17
    assert row["playback_position_s"] == 9
    assert "no automatic dataset replay" in row["error"]
    assert act(db, make(db), "start")["state"] == "preparing"


def test_authorization_and_site_profile(db, monkeypatch, tmp_path):
    users = tmp_path / "users.json"
    users.write_text(
        json.dumps(
            {
                hashlib.sha256(b"viewer-token").hexdigest(): {"actor": "v", "role": "viewer"},
                hashlib.sha256(b"operator-token").hexdigest(): {"actor": "o", "role": "operator"},
            }
        )
    )
    monkeypatch.setenv("TWINGUARD_USERS", str(users))
    c = TestClient(app)
    assert c.get("/api/v1/demo/scenarios").status_code == 401
    headers = {"Authorization": "Bearer viewer-token", "Idempotency-Key": str(uuid.uuid4())}
    assert c.get("/api/v1/demo/scenarios", headers=headers).status_code == 200
    assert c.post("/api/v1/demo/sessions", headers=headers, json={}).status_code == 403
    headers["Authorization"] = "Bearer operator-token"
    monkeypatch.setenv("TWINGUARD_PROFILE", "site-review")
    assert c.post("/api/v1/demo/sessions", headers=headers, json={}).status_code == 403
    monkeypatch.setenv("TWINGUARD_PROFILE", "simulation")
    row = c.post("/api/v1/demo/sessions", headers=headers, json={})
    assert row.status_code == 200
    assert (
        c.post("/api/v1/demo/sessions", headers=headers, json={}).json()["id"] == row.json()["id"]
    )


def test_accepted_session_provenance_and_duplicate(db):
    source = SourceRegistration(
        source_id="demo-iot",
        transport_identity="demo-iot",
        sensors={
            "pressure-01": {"asset_id": "BW-01", "measurement_type": "pressure", "unit": "Pa"}
        },
        clock_quality="synchronized",
        clock_basis="controlled_simulation_replay",
        calibration_status="assumed_simulation",
        calibration_reference="test",
    )
    with db.begin() as c:
        put(c, "source", source.source_id, source.model_dump(mode="json"))
    stamp = now() - timedelta(seconds=1)
    obs = SensorObservation(
        observation_id="public-sample",
        sensor_id="pressure-01",
        asset_id="BW-01",
        measurement_type="pressure",
        value=1300000,
        unit="Pa",
        quality="good",
        acquired_at=stamp,
        received_at=stamp,
        provenance_id="original-scientific",
        location_reference="BW-01",
        source_type="synthetic",
        clock_quality="synchronized",
    )
    env = Envelope(
        message_id="demo-delivery",
        source_id="demo-iot",
        sequence=0,
        sequence_epoch="demo-session",
        emitted_at=now(),
        provenance_id="demo-session",
        mode="simulation_replay",
        replay_acquired_at=stamp,
        observation=obs,
    )
    raw = env.model_dump_json().encode()
    assert ingest(db, raw, "demo-iot", topic("demo-iot"))["status"] == "accepted"
    assert ingest(db, raw, "demo-iot", topic("demo-iot"))["status"] == "duplicate"
    with db.connect() as c:
        row = c.execute(select(observations)).mappings().one()
    assert row["metadata"]["demo_session_id"] == "demo-session"
    assert row["body"]["provenance_id"] == "original-scientific"
    assert not any(key in row["body"] for key in ("ground_truth", "true_pose", "fault_labels"))
    assert row["body"]["acquired_at"] == obs.model_dump(mode="json")["acquired_at"]


def test_runtime_image_excludes_privileged_controller():
    root = Path(__file__).resolve().parents[1]
    api_image = (root / "deployment/edge/Dockerfile.api").read_text()
    assert "COPY src/twinguard/demo" not in api_image
    assert "COPY src/twinguard/plant" not in api_image
    assert "COPY scripts/edge_demo" not in api_image
