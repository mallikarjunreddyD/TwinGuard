"""Operational trust, transactional recovery and API integration tests."""

import hashlib
import io
import json
import zipfile
from datetime import timedelta
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from twinguard.edge.contracts import SourceRegistration, Envelope, now
from twinguard.edge.storage import (
    engine,
    metadata,
    put,
    get,
    observations,
    jobs,
    claim,
    retain,
    inbox,
)
from twinguard.edge.ingestion import ingest, topic
from twinguard.edge.artifacts import ArtifactStore
from twinguard.edge.worker import run_one, checkpoint
from twinguard.fusion.models import FusionState
from twinguard.core.contracts import SensorObservation


@pytest.fixture
def db(tmp_path, monkeypatch):
    url = "sqlite:///" + str(tmp_path / "edge.db")
    monkeypatch.setenv("TWINGUARD_DB", url)
    monkeypatch.setenv("TWINGUARD_PROFILE", "simulation")
    e = engine(url)
    metadata.create_all(e)
    source = SourceRegistration(
        source_id="test-source",
        transport_identity="test-identity",
        sensors={
            "pressure-01": {"asset_id": "BW-01", "measurement_type": "pressure", "unit": "Pa"}
        },
        calibration_status="assumed_simulation",
        calibration_reference="assumed-v1",
        clock_quality="synchronized",
        clock_basis="controlled_simulation_replay",
    )
    with e.begin() as c:
        put(c, "source", source.source_id, source.model_dump(mode="json"))
        put(c, "checkpoint", "F1", FusionState().model_dump(mode="json"))
    yield e
    e.dispose()


def sample(ident="sample-1", value=1300000.0):
    t = now() - timedelta(seconds=1)
    return SensorObservation(
        observation_id=ident,
        sensor_id="pressure-01",
        asset_id="BW-01",
        measurement_type="pressure",
        value=value,
        unit="Pa",
        quality="good",
        acquired_at=t,
        received_at=t,
        provenance_id="test-public",
        location_reference="BW-01",
        source_type="synthetic",
        clock_quality="synchronized",
    )


def env(obs=None, **kwargs):
    return Envelope(
        message_id="message-1",
        source_id="test-source",
        sequence=1,
        emitted_at=now(),
        provenance_id="test-public",
        observation=obs or sample(),
        **kwargs,
    )


def send(db, e, identity="test-identity", received_topic=None):
    return ingest(
        db, e.model_dump_json().encode(), identity, received_topic or topic("test-source")
    )


def test_durable_observation_and_duplicate(db):
    e = env()
    assert send(db, e)["status"] == "accepted"
    assert send(db, e)["status"] == "duplicate"
    with db.connect() as c:
        assert c.execute(select(func.count()).select_from(observations)).scalar_one() == 1
        assert c.execute(select(func.count()).select_from(jobs)).scalar_one() == 1


@pytest.mark.parametrize(
    "identity,received_topic", [("attacker", None), ("test-identity", topic("another-source"))]
)
def test_identity_and_topic_separate_from_payload(db, identity, received_topic):
    assert send(db, env(), identity, received_topic)["status"] == "quarantined"
    with db.connect() as c:
        assert c.execute(select(func.count()).select_from(observations)).scalar_one() == 0


@pytest.mark.parametrize(
    "changes",
    [{"asset_id": "DR-01"}, {"sensor_id": "pressure-02"}, {"configuration_version": "unknown"}],
)
def test_source_mapping_configuration(db, changes):
    e = env(sample().model_copy(update=changes))
    assert send(db, e)["status"] == "quarantined"


@pytest.mark.parametrize("raw", [b"{}", b"invalid", b"x" * 131073, b'{"value":NaN}'])
def test_invalid_oversized_input_quarantined(db, raw):
    assert ingest(db, raw, "test-identity", topic("test-source"))["status"] == "quarantined"


def test_future_and_malformed_order(db):
    obs = sample()
    obs = obs.model_copy(
        update={
            "acquired_at": now() + timedelta(seconds=60),
            "received_at": now() + timedelta(seconds=61),
        }
    )
    assert send(db, env(obs))["status"] == "quarantined"


def test_payload_clock_does_not_establish_trust(db):
    with db.begin() as c:
        source = get(c, "source", "test-source")
        source["clock_quality"] = "unknown"
        source["calibration_status"] = "unknown"
        put(c, "source", "test-source", source)
    assert send(db, env())["status"] == "accepted"
    assert run_one(db, "iot", "test-worker")
    with db.connect() as c:
        row = c.execute(select(observations)).mappings().one()
        assert row["metadata"]["trusted_clock_quality"] == "unknown"
        assert get(c, "condition", "BW-01")["assessment"]["severity"] != "red"


def test_critical_raw_without_load_or_uav_and_ack(db):
    assert send(db, env())["status"] == "accepted"
    assert run_one(db, "iot", "test-worker")
    # Reopen engine (API/worker restart): all state is durable, not process memory.
    with engine().connect() as c:
        state = FusionState.model_validate(get(c, "checkpoint", "F1"))
        condition = get(c, "condition", "BW-01")
        assert condition["assessment"]["severity"] == "red"
        event = next(e for e in state.events.values() if e.severity == "red")
    from twinguard.fusion.models import OperatorAction

    action = OperatorAction(
        action_id="ack-test",
        asset_id="BW-01",
        hazard_id=event.hazard_id,
        at=now(),
        kind="acknowledge",
        rationale="Qualified operator review",
    )
    with db.begin() as c:
        checkpoint(c, [], [action])
        checkpoint(c, [], [action])
        state = FusionState.model_validate(get(c, "checkpoint", "F1"))
        assert len([n for n in state.notices if n.transition == "acknowledged"]) <= 1
        assert get(c, "condition", "BW-01")["assessment"]["severity"] == "red"


def test_conflicting_identity_rolls_back(db):
    e = env()
    send(db, e)
    second = e.model_copy(update={"observation": sample(value=900000.0)})
    assert send(db, second)["status"] == "quarantined"
    with db.connect() as c:
        assert c.execute(select(observations.c.body)).scalar_one()["value"] == 1300000.0


def test_lease_recovery(db):
    send(db, env())
    job = claim(db, "iot", "crashed", lease_s=-1)
    assert job
    assert run_one(engine(), "iot", "restarted")
    with db.connect() as c:
        result = c.execute(select(jobs)).mappings().one()
        assert result["status"] == "completed" and result["attempts"] == 2
        assert get(c, "condition", "BW-01")["assessment"]["severity"] == "red"


def test_transaction_rollback(db):
    with pytest.raises(RuntimeError):
        with db.begin() as c:
            put(c, "test", "rollback", {"value": 1})
            raise RuntimeError("crash before commit")
    with db.connect() as c:
        assert get(c, "test", "rollback") is None


def test_retention_preserves_unresolved_history(db):
    send(db, env())
    run_one(db, "iot", "worker")
    with db.begin() as c:
        c.execute(inbox.update().values(received=(now() - timedelta(days=91)).isoformat()))
    assert retain(db) == 1
    with db.connect() as c:
        assert get(c, "archive", "message-1")
        assert get(c, "checkpoint", "F1")["events"]
        assert c.execute(select(func.count()).select_from(observations)).scalar_one() == 1


@pytest.mark.parametrize(
    "name",
    ["../secrets", "/etc/passwd", "evaluation_private/truth.json", "observations/../../x.json"],
)
def test_artifact_confinement(tmp_path, name):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr(name, "{}")
    with pytest.raises(ValueError):
        ArtifactStore(tmp_path / "objects").upload(b.getvalue())


def test_artifact_hash_and_key(tmp_path):
    store = ArtifactStore(tmp_path)
    with pytest.raises(ValueError):
        store.path("../etc/passwd")
    digest = hashlib.sha256(b"original").hexdigest()
    store.path(digest).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        store.verify_bundle(digest)


def test_api_roles_and_idempotent_ack(db, tmp_path, monkeypatch):
    users = {
        hashlib.sha256(k.encode()).hexdigest(): {"actor": k, "role": k}
        for k in ["viewer", "operator"]
    }
    path = tmp_path / "users.json"
    path.write_text(json.dumps(users))
    monkeypatch.setenv("TWINGUARD_USERS", str(path))
    from twinguard.api.app import app

    client = TestClient(app)
    assert client.get("/api/v1/assets").status_code == 401
    assert (
        client.get("/api/v1/assets", headers={"Authorization": "Bearer viewer"}).status_code == 200
    )
    send(db, env())
    run_one(db, "iot", "worker")
    events = client.get("/api/v1/events", headers={"Authorization": "Bearer viewer"}).json()
    event = next(e for e in events if e["severity"] == "red")
    url = "/api/v1/events/" + event["event_id"] + "/acknowledge"
    assert (
        client.post(
            url, headers={"Authorization": "Bearer viewer"}, json={"rationale": "review"}
        ).status_code
        == 403
    )
    first = client.post(
        url, headers={"Authorization": "Bearer operator"}, json={"rationale": "review"}
    )
    assert first.status_code == 200
    assert (
        client.post(
            url, headers={"Authorization": "Bearer operator"}, json={"rationale": "repeat review"}
        ).json()
        == first.json()
    )
    assert (
        client.get(
            "/api/v1/artifacts/" + "a" * 64, headers={"Authorization": "Bearer viewer"}
        ).status_code
        == 404
    )


def test_site_review_no_illustrative_critical(db, monkeypatch):
    monkeypatch.setenv("TWINGUARD_PROFILE", "site-review")
    send(db, env())
    run_one(db, "iot", "worker")
    with db.connect() as c:
        assert get(c, "condition", "BW-01")["assessment"]["severity"] != "red"


def test_policy_mismatch_requires_explicit_reassessment(db, monkeypatch):
    send(db, env())
    run_one(db, "iot", "worker")
    monkeypatch.setenv("TWINGUARD_PROFILE", "site-review")
    with pytest.raises(ValueError, match="policy"):
        with db.begin() as c:
            checkpoint(c, [])


def test_edge_has_no_private_imports():
    from twinguard.core.boundaries import forbidden_imports

    root = Path("src/twinguard/edge")
    for p in root.glob("*.py"):
        assert forbidden_imports(p, "twinguard.edge." + p.stem) == []


def test_compaction_preserves_historical_active_support(db):
    send(db, env())
    run_one(db, "iot", "worker")
    with db.begin() as c:
        before = get(c, "checkpoint", "F1")
        protected = {k for event in before["events"].values() for k in event["positive_ids"]}
        # Age the retained evidence (an explicit test clock), preserving original event references.
        state = FusionState.model_validate(before)
        for e in state.evidence.values():
            e.acquired_at = e.acquired_at - timedelta(days=1)
        put(c, "checkpoint", "F1", state.model_dump(mode="json"))
        checkpoint(c, [])
        after = get(c, "checkpoint", "F1")
        assert protected <= set(after["evidence"])
        assert get(c, "condition", "BW-01")["assessment"]["severity"] == "red"


def test_archived_message_still_rejects_conflicting_payload(db):
    first = env()
    assert send(db, first)["status"] == "accepted"
    with db.begin() as c:
        c.execute(inbox.update().values(received=(now() - timedelta(days=91)).isoformat()))
    retain(db)
    assert send(db, first)["status"] == "duplicate"
    other = first.model_copy(update={"observation": sample("different-physical-observation")})
    assert send(db, other)["status"] == "quarantined"


def test_future_publisher_clock_rejected(db):
    e = env().model_copy(update={"emitted_at": now() + timedelta(seconds=30)})
    assert send(db, e)["status"] == "quarantined"


def test_operating_context_never_crosses_dataset_provenance(db, monkeypatch):
    # Separate replay datasets can share original simulation timestamps. They are not one measured load history.
    from twinguard.edge import worker

    target = sample()
    foreign = sample("foreign-source").model_copy(update={"provenance_id": "another-dataset"})
    with db.begin() as c:
        c.execute(
            observations.insert().values(
                id=foreign.observation_id,
                asset=foreign.asset_id,
                sensor=foreign.sensor_id,
                acquired=foreign.acquired_at.isoformat(),
                received=foreign.received_at.isoformat(),
                source="other",
                body=foreign.model_dump(mode="json"),
                metadata={},
            )
        )
    original = worker.infer_operating

    def checked(records, model, config):
        assert all(r.provenance_id == target.provenance_id for r in records)
        return original(records, model, config)

    monkeypatch.setattr(worker, "infer_operating", checked)
    assert send(db, env(target))["status"] == "accepted"
    assert worker.run_one(db, "iot", "worker")
    with db.connect() as c:
        assert c.execute(select(jobs.c.status)).scalar_one() == "completed"
        assert c.execute(
            select(observations.c.metadata).where(observations.c.id == target.observation_id)
        ).scalar_one()["ingest_commit_confirmed_at"]


def test_capture_replay_clock_preserves_relative_acquisitions():
    from twinguard.edge.worker import mapped_capture_time

    source = now() - timedelta(days=1)
    wall = now()
    meta = {
        "mode": "simulation_replay",
        "replay_rate": 5,
        "effective_acquired_at": wall.isoformat(),
        "replay_source_anchor_at": source.isoformat(),
    }
    assert mapped_capture_time(source, meta) == wall
    assert mapped_capture_time(source - timedelta(seconds=60), meta) == wall - timedelta(seconds=12)
    assert mapped_capture_time(source, {"mode": "live"}) == source


def test_duplicate_representation_changes_transport_not_measurement(db):
    observation = sample()
    first = env(observation)
    assert send(db, first)["status"] == "accepted"
    duplicate = observation.model_copy(
        update={
            "received_at": observation.received_at + timedelta(seconds=0.01),
            "delivery_status": "duplicate",
        }
    )
    second = first.model_copy(
        update={"message_id": "other-transport-delivery", "observation": duplicate, "sequence": 2}
    )
    assert send(db, second)["status"] == "duplicate"
    with db.connect() as c:
        assert c.execute(select(func.count()).select_from(observations)).scalar_one() == 1
        assert c.execute(select(func.count()).select_from(jobs)).scalar_one() == 1


def test_source_epoch_reset_and_actual_out_of_order_acquisition(db):
    first = env().model_copy(update={"sequence": 50, "sequence_epoch": "replay-one"})
    assert send(db, first)["status"] == "accepted"
    second = env(sample("next-dataset")).model_copy(
        update={"message_id": "next-epoch", "sequence": 0, "sequence_epoch": "replay-two"}
    )
    assert send(db, second)["status"] == "accepted"
    from twinguard.edge.storage import list_records

    with db.connect() as c:
        audits = list_records(c, "audit")
        assert not any(a["reason"] == "out_of_order" for a in audits)
        assert get(c, "source_health", "test-source")["last_sequence"] == 0


def test_explicit_failed_job_retry_is_audited_and_preserves_input(db):
    from twinguard.edge.admin import retry_failed

    send(db, env())
    with pytest.raises(ValueError):
        retry_failed(db, "sample-1", "cannot retry pending work")
    with db.begin() as c:
        original = c.execute(select(jobs.c.body)).scalar_one()
        c.execute(
            jobs.update().values(status="failed", attempts=3, error="missing runtime dependency")
        )
    retry_failed(db, "sample-1", "runtime dependency corrected")
    assert run_one(db, "iot", "recovered")
    with db.connect() as c:
        assert c.execute(select(jobs.c.body)).scalar_one() == original
        assert c.execute(select(jobs.c.status)).scalar_one() == "completed"


def test_qualified_critical_reading_preempts_ordinary_backlog(db):
    regular = env(sample("ordinary", 900000.0)).model_copy(
        update={"message_id": "ordinary-message"}
    )
    critical = env(sample("urgent", 1300000.0)).model_copy(
        update={"message_id": "urgent-message", "sequence": 2}
    )
    assert send(db, regular)["status"] == "accepted"
    assert send(db, critical)["status"] == "accepted"
    assert claim(db, "iot", "prioritized")["id"] == "urgent"
    assert claim(db, "iot", "ordinary")["id"] == "ordinary"


@pytest.mark.parametrize("trust", ["unknown-clock", "unknown-calibration"])
def test_unqualified_reading_cannot_gain_critical_priority(db, trust):
    with db.begin() as c:
        source = get(c, "source", "test-source")
        source["clock_quality" if trust == "unknown-clock" else "calibration_status"] = "unknown"
        put(c, "source", "test-source", source)
    assert send(db, env())["status"] == "accepted"
    with db.connect() as c:
        assert c.execute(select(jobs.c.body)).scalar_one()["priority"] == 10


def test_exhausted_crash_lease_is_quarantined(db):
    send(db, env())
    claim(db, "iot", "crashed", lease_s=-1)
    with db.begin() as c:
        c.execute(jobs.update().values(attempts=3))
    assert claim(db, "iot", "retry") is None
    with db.connect() as c:
        assert c.execute(select(jobs.c.status)).scalar_one() == "failed"
