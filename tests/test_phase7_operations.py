"""Recoverable raw archives preserve unresolved work, deduplication and scientific state."""

import hashlib
import pytest
from sqlalchemy import create_engine, select
from twinguard.edge.storage import metadata, inbox, jobs, records, put, get
from twinguard.edge.archive import archive_raw, recover_raw


def test_archive_preserves_unresolved_work_and_scientific_history(tmp_path):
    db = create_engine("sqlite:///" + str(tmp_path / "db.sqlite"))
    metadata.create_all(db)
    with db.begin() as c:
        for ident, status in (("done", "completed"), ("waiting", "pending")):
            c.execute(
                inbox.insert().values(
                    id=ident,
                    source="test-source",
                    digest=hashlib.sha256(ident.encode()).hexdigest(),
                    received="2020-01-01T00:00:00+00:00",
                    status="accepted",
                    body={"payload": ident},
                )
            )
            c.execute(jobs.insert().values(id=ident, kind="iot", status=status))
        put(c, "event", "unresolved-event", {"support": ["evidence-1"], "active": True})
        put(c, "evidence", "evidence-1", {"finding": "positive", "provenance_id": "preserve-me"})
    result = archive_raw(db, tmp_path / "archive", days=90)
    assert result["rows"] == 1
    with db.connect() as c:
        assert c.execute(select(inbox.c.id)).scalars().all() == ["waiting"]
        assert recover_raw(c, "done", tmp_path / "archive")["body"] == {"payload": "done"}
        assert get(c, "archive", "done")["digest"] == hashlib.sha256(b"done").hexdigest()
        assert get(c, "event", "unresolved-event")["support"] == ["evidence-1"]
        assert get(c, "evidence", "evidence-1")["provenance_id"] == "preserve-me"
        assert c.execute(
            select(records.c.id).where(records.c.kind == "archive")
        ).scalars().all() == ["done"]
    assert archive_raw(db, tmp_path / "archive", days=90)["rows"] == 0
    path = tmp_path / "archive" / result["sha256"]
    path.write_bytes(b"corrupt")
    with db.connect() as c, pytest.raises(ValueError, match="checksum"):
        recover_raw(c, "done", tmp_path / "archive")


@pytest.mark.parametrize("days,limit", [(-1, 1), (90, 0), (90, 257)])
def test_archive_rejects_unbounded_policy(tmp_path, days, limit):
    with pytest.raises(ValueError):
        archive_raw(None, tmp_path, days=days, limit=limit)


def test_external_destination_guard_checks_actual_drive_and_source_floor(tmp_path, monkeypatch):
    import shutil
    from twinguard.evaluation.campaigns import resource_preflight

    stats = type(shutil.disk_usage("/"))
    monkeypatch.setenv("TWINGUARD_CAMPAIGN_STORAGE", str(tmp_path))

    def usage(path):
        free = 3 if str(path) == "/mnt/c" else 50
        return stats(100 * 1024**3, (100 - free) * 1024**3, free * 1024**3)

    monkeypatch.setattr(shutil, "disk_usage", usage)
    result = resource_preflight(reserve_bytes=5 * 1024**3)
    assert result["source_host"]["reserved_bytes"] == 0
    assert result["destination"]["reserved_bytes"] == 5 * 1024**3
    monkeypatch.setattr(shutil, "disk_usage", lambda p: stats(100 * 1024**3, 100 * 1024**3, 0))
    with pytest.raises(RuntimeError):
        resource_preflight()


@pytest.mark.parametrize(
    "depth,value,quality,clock,age,accepted",
    [
        (10000, 1300000.0, "good", "synchronized", 1, True),
        (10000, 1000000.0, "good", "synchronized", 1, False),
        (10000, 1300000.0, "unknown", "synchronized", 1, False),
        (10000, 1300000.0, "good", "unknown", 1, False),
        (10000, 1300000.0, "good", "synchronized", 20, False),
        (10100, 1300000.0, "good", "synchronized", 1, False),
    ],
)
def test_reserved_admission_is_bounded_current_and_independently_qualified(
    tmp_path, monkeypatch, depth, value, quality, clock, age, accepted
):
    from datetime import timedelta
    from twinguard.edge.contracts import SourceRegistration, Envelope, now
    from twinguard.core.contracts import SensorObservation
    from twinguard.edge.ingestion import ingest, topic

    db = create_engine("sqlite:///" + str(tmp_path / "admission.sqlite"))
    metadata.create_all(db)
    monkeypatch.setenv("TWINGUARD_PROFILE", "simulation")
    source = SourceRegistration(
        source_id="test-source",
        transport_identity="test-identity",
        sensors={
            "pressure-01": {"asset_id": "BW-01", "measurement_type": "pressure", "unit": "Pa"}
        },
        calibration_status="assumed_simulation",
        clock_quality=clock,
    )
    with db.begin() as c:
        put(c, "source", source.source_id, source.model_dump(mode="json"))
        c.execute(
            jobs.insert(),
            [
                {"id": f"capacity-{i}", "kind": "capacity_fixture", "status": "pending"}
                for i in range(depth)
            ],
        )
    obs = SensorObservation(
        observation_id="actual",
        sensor_id="pressure-01",
        asset_id="BW-01",
        measurement_type="pressure",
        value=value,
        unit="Pa",
        quality=quality,
        acquired_at=now() - timedelta(seconds=age),
        received_at=now(),
        provenance_id="test-public",
        location_reference="BW-01",
        source_type="synthetic",
        clock_quality=clock,
    )
    envelope = Envelope(
        message_id="actual-envelope",
        source_id="test-source",
        sequence=0,
        emitted_at=now(),
        provenance_id=obs.provenance_id,
        observation=obs,
    )
    result = ingest(db, envelope.model_dump_json().encode(), "test-identity", topic("test-source"))
    assert (result["status"] == "accepted") == accepted
    with db.connect() as c:
        count = c.execute(select(jobs.c.id).where(jobs.c.id == obs.observation_id)).first()
        assert bool(count) == accepted
