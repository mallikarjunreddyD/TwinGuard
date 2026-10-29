"""Measured adversarial loopback checks; no scientific observations are inserted by these invalid cases."""

import argparse
import hashlib
import io
import json
import time
import zipfile
from datetime import timedelta
from pathlib import Path
import httpx
from sqlalchemy import select
from twinguard.edge.storage import engine, records
from twinguard.edge.contracts import Envelope, now
from twinguard.edge.ingestion import topic
from twinguard.edge.protocols import mqtt_client
from twinguard.core.observations import load_public_observations
from twinguard.core.contracts import SensorObservation


def main(output):
    if output.exists():
        raise ValueError("New output required")
    secrets = json.loads(Path(".edge/secrets.json").read_text())
    db = engine(
        "postgresql+psycopg://twinguard:" + secrets["database"] + "@127.0.0.1:18982/twinguard"
    )
    sample = next(
        r
        for r in load_public_observations(Path("experiments/outputs/e4-public-8200"))
        if isinstance(r, SensorObservation) and r.sensor_id == "pressure-01"
    )
    env = Envelope(
        message_id="invalid-phase7-security",
        source_id="demo-iot",
        sequence=900000,
        emitted_at=now(),
        observation=sample,
        provenance_id=sample.provenance_id,
        mode="simulation_replay",
        replay_acquired_at=now(),
    )
    good = env.model_dump(mode="json")
    cases = {"invalid_schema": b"{}"}
    for kind in [
        "wrong_asset",
        "wrong_unit",
        "unregistered_source",
        "future_timestamp",
        "nonfinite",
    ]:
        value = json.loads(json.dumps(good))
        value["message_id"] += "-" + kind
        if kind == "wrong_asset":
            value["observation"]["asset_id"] = "DR-01"
        if kind == "wrong_unit":
            value["observation"]["unit"] = "degC"
        if kind == "unregistered_source":
            value["source_id"] = "unregistered-source"
        if kind == "future_timestamp":
            value["replay_acquired_at"] = (now() + timedelta(seconds=60)).isoformat()
        if kind == "nonfinite":
            value["observation"]["value"] = float("nan")
        cases[kind] = json.dumps(value).encode()
    client = mqtt_client("demo-iot", secrets["demo-iot"], "edge-security")
    client.connect("localhost", 18983)
    client.loop_start()
    try:
        for raw in cases.values():
            client.publish(topic("demo-iot"), raw, qos=1).wait_for_publish(5)
    finally:
        client.disconnect()
        client.loop_stop()
    time.sleep(3)
    with db.connect() as c:
        audit = list(c.execute(select(records.c.body).where(records.c.kind == "audit")).scalars())
    results = {
        name: {
            "quarantined": any(
                a.get("digest") == hashlib.sha256(raw).hexdigest() and a["reason"] == "quarantined"
                for a in audit
            )
        }
        for name, raw in cases.items()
    }
    url = "http://localhost:18980/api/v1/"
    results["anonymous_api"] = {"status": httpx.get(url + "assets").status_code}
    results["viewer_operator_action"] = {
        "status": httpx.post(
            url + "events/absent/acknowledge",
            headers={"Authorization": "Bearer " + secrets["viewer"]},
            json={"rationale": "attempt unauthorized review"},
        ).status_code
    }
    results["private_artifact"] = {
        "status": httpx.get(
            url + "artifacts/" + "a" * 64, headers={"Authorization": "Bearer " + secrets["viewer"]}
        ).status_code
    }
    for name, path in [
        ("path_traversal", "../secret.json"),
        ("private_scope", "evaluation_private/truth.json"),
    ]:
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w") as z:
            z.writestr(path, "{}")
        response = httpx.post(
            url + "inspection-imports",
            headers={"Authorization": "Bearer " + secrets["operator"]},
            content=b.getvalue(),
        )
        results[name] = {"status": response.status_code, "detail": response.json()}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"executed_at": now().isoformat(), "results": results}, indent=2) + "\n"
    )
    print(results)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    main(a.output)
