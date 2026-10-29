"""Interruptible shared publisher preserves original data and explicit replay clocks."""

from datetime import timedelta
import json
import threading
import time
from scripts import edge_demo
from twinguard.core.contracts import SensorObservation
from twinguard.edge.contracts import Envelope, now
from twinguard.edge import protocols


class Info:
    def wait_for_publish(self, timeout):
        pass

    def is_published(self):
        return True


class Client:
    def __init__(self):
        self.messages = []

    def connect(self, host, port):
        pass

    def loop_start(self):
        pass

    def disconnect(self):
        pass

    def loop_stop(self):
        pass

    def publish(self, topic, payload, qos):
        self.messages.append(Envelope.model_validate_json(payload))
        return Info()


class Hooks:
    def __init__(self, action):
        self.desired = "running"
        self.action = action
        self.first = threading.Event()
        self.paused = threading.Event()

    def ready(self, total, source, wall):
        assert total == 2

    def control(self):
        return self.desired

    def state(self, state):
        if state == "paused":
            self.paused.set()

    def published(self, count, record, delivery, position):
        if count == 1:
            self.desired = self.action
            self.first.set()


def setup(tmp_path, monkeypatch):
    original = now() - timedelta(days=1)
    rows = [
        SensorObservation(
            observation_id="sample-" + str(i),
            sensor_id="pressure-01",
            asset_id="BW-01",
            measurement_type="pressure",
            value=1000000 + i,
            unit="Pa",
            quality="good",
            acquired_at=original + timedelta(seconds=i * 0.2),
            received_at=original + timedelta(seconds=i * 0.2),
            provenance_id="original-public-science",
            location_reference="BW-01",
            source_type="synthetic",
            clock_quality="synchronized",
        )
        for i in range(2)
    ]
    monkeypatch.setattr(edge_demo, "load_public_observations", lambda path: rows)
    client = Client()
    monkeypatch.setattr(protocols, "mqtt_client", lambda *args: client)
    credentials = tmp_path / "controller.json"
    credentials.write_text(json.dumps({"demo-iot": "test-only"}))
    return rows, client, credentials


def test_actual_pause_suspends_publication_and_preserves_clock(tmp_path, monkeypatch):
    rows, client, credentials = setup(tmp_path, monkeypatch)
    hooks = Hooks("paused")
    errors = []

    def run():
        try:
            edge_demo.stream(
                tmp_path,
                tmp_path / "publisher",
                speed=1,
                inspections=False,
                hooks=hooks,
                secrets_file=credentials,
                session_id="demo-test",
            )
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    assert hooks.first.wait(3) and hooks.paused.wait(3)
    time.sleep(0.3)
    assert len(client.messages) == 1
    hooks.desired = "running"
    thread.join(4)
    assert not thread.is_alive() and not errors
    assert [x.sequence for x in client.messages] == [0, 1]
    assert all(
        x.sequence_epoch == "demo-test" and x.source_id == "demo-iot" for x in client.messages
    )
    assert [x.observation.acquired_at for x in client.messages] == [x.acquired_at for x in rows]
    assert (
        client.messages[1].replay_acquired_at - client.messages[0].replay_acquired_at
    ).total_seconds() >= 0.45
    assert all(x.emitted_at >= x.replay_acquired_at for x in client.messages)


def test_stop_ends_only_publisher_without_second_delivery(tmp_path, monkeypatch):
    rows, client, credentials = setup(tmp_path, monkeypatch)
    hooks = Hooks("stopped")
    import pytest

    with pytest.raises(edge_demo.ReplayStopped):
        edge_demo.stream(
            tmp_path,
            tmp_path / "publisher",
            speed=1,
            inspections=False,
            hooks=hooks,
            secrets_file=credentials,
            session_id="demo-test",
        )
    assert len(client.messages) == 1
    assert client.messages[0].observation == rows[0]
