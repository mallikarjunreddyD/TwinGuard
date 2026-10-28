"""Privileged local scenario controller; publishes ONLY public measured observations."""

import argparse
import io
import json
import time
import zipfile
from pathlib import Path
from datetime import timedelta
import httpx
from twinguard.core.contracts import SensorObservation, InspectionSchedule
from twinguard.core.observations import load_public_observations
from twinguard.edge.contracts import Envelope, now
from twinguard.edge.protocols import publish

ROOT = Path(__file__).resolve().parents[1]


def generate(output, seed=8100, kind="critical", fidelity="L1"):
    # Only the controller imports generation. None of these modules exist in runtime images.
    from twinguard.evaluation.experiments import setup_scenario
    from twinguard.plant.config import load_plant_config
    from twinguard.plant.model import create_baseline_plant
    from twinguard.plant.simulator import PlantSimulator
    from twinguard.sensing.acquisition import acquire, load_installation

    scenario, faults = setup_scenario(
        ROOT,
        output.name,
        seed,
        kind="geometric"
        if kind == "geometry"
        else "thermal"
        if kind == "thermal"
        else "process"
        if kind == "critical"
        else None,
        amplitude=0.02,
    )
    if kind == "critical":
        faults[0].true_process_deviation = 500000
    scenario.fault_config_references = [f.fault_id for f in faults]
    installation = load_installation(ROOT / f"configs/sensing/{fidelity}.yaml")
    scenario.sensor_config_ids = [installation.lidar.sensor_id, installation.thermal.sensor_id] + [
        s.sensor_id for s in installation.iot
    ]
    scenario.inspections = [
        InspectionSchedule(sensor_id=installation.lidar.sensor_id, offset_s=t, modality="lidar")
        for t in [0, 60]
    ] + [
        InspectionSchedule(sensor_id=installation.thermal.sensor_id, offset_s=t, modality="thermal")
        for t in [0, 60]
    ]
    simulator = PlantSimulator(
        create_baseline_plant(load_plant_config(ROOT / "configs/plant.yaml"), seed),
        scenario,
        faults,
    )
    acquire(simulator.sensing_reader(), scenario, installation, output)
    return output


def bundle(data):
    # Exact public manifest and referenced observations only; no private directories or scenario files.
    from twinguard.core.observations import validate_import_manifest

    manifest = validate_import_manifest(data)
    names = (
        {"manifest.json"}
        | {a.uri for a in manifest.artifacts}
        | {r.record_uri for r in manifest.observations}
    )
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(names):
            z.write(data / name, name)
    return content.getvalue()


def stream(
    data,
    output,
    url="http://localhost:18780",
    host="localhost",
    port=18783,
    speed=20,
    inspections=True,
    duplicates=False,
    reverse=False,
    limit=None,
    step=False,
    control_file=None,
):
    if speed <= 0:
        raise ValueError("Playback speed must be positive")
    output.mkdir(parents=True, exist_ok=False)
    secrets = json.loads((ROOT / ".edge/secrets.json").read_text())
    samples = [r for r in load_public_observations(data) if isinstance(r, SensorObservation)]
    samples = sorted(samples, key=lambda r: (r.acquired_at, r.sensor_id))
    if limit:
        samples = samples[:limit]
    if reverse:
        samples = list(reversed(samples))
    start = time.monotonic()
    source_begin = min(r.acquired_at for r in samples)
    wall_begin = now()
    sent = []
    # One real MQTT connection, QoS1 PUBACK per message; local replay pacing is wall-clock measured.
    from twinguard.edge.protocols import mqtt_client
    from twinguard.edge.ingestion import topic

    client = mqtt_client("demo-iot", secrets["demo-iot"], "publisher-demo-iot")
    client.connect(host, port)
    client.loop_start()
    try:
        for seq, record in enumerate(samples):
            if step:
                input("Enter to publish next measured observation: ")
            paused = time.monotonic()
            while (
                control_file
                and control_file.exists()
                and json.loads(control_file.read_text()).get("paused", False)
            ):
                time.sleep(0.1)
            adjustment = time.monotonic() - paused
            start += adjustment
            wall_begin += timedelta(seconds=adjustment)
            offset = (record.acquired_at - source_begin).total_seconds() / speed
            if not reverse:
                time.sleep(max(0, start + offset - time.monotonic()))
            emission = now()
            # Original scientific record unchanged. Mapped acquisition remains causal and explicit.
            effective = (
                wall_begin + timedelta(seconds=offset)
                if not reverse
                else emission - timedelta(seconds=(len(samples) - seq) * 0.01)
            )
            effective = min(effective, emission)
            env = Envelope(
                message_id="mqtt-" + record.observation_id,
                source_id="demo-iot",
                sequence=seq,
                emitted_at=emission,
                mode="simulation_replay",
                replay_acquired_at=effective,
                observation=record,
                provenance_id=record.provenance_id,
            )
            payload = env.model_dump_json()
            repeats = 2 if duplicates and seq % 3 == 0 else 1
            for repeat in range(repeats):
                info = client.publish(topic("demo-iot"), payload, qos=1)
                info.wait_for_publish(timeout=20)
                if not info.is_published():
                    raise RuntimeError("No MQTT PUBACK")
                sent.append(
                    {
                        "message_id": env.message_id,
                        "observation_id": record.observation_id,
                        "original_acquired_at": record.acquired_at.isoformat(),
                        "effective_acquired_at": effective.isoformat(),
                        "emitted_at": emission.isoformat(),
                        "puback_at": now().isoformat(),
                        "duplicate": repeat > 0,
                    }
                )
    finally:
        client.disconnect()
        client.loop_stop()
    if inspections:
        data_bytes = bundle(data)
        response = httpx.post(
            url + "/api/v1/inspection-imports",
            content=data_bytes,
            headers={"Authorization": "Bearer " + secrets["operator"]},
            timeout=120,
        )
        response.raise_for_status()
        digest = response.json()["sha256"]
        env = Envelope(
            message_id="inspection-" + data.name,
            source_id="demo-uav",
            kind="inspection",
            sequence=0,
            emitted_at=now(),
            mode="simulation_replay",
            replay_acquired_at=now(),
            artifact_sha256=digest,
            provenance_id="public-" + data.name,
        )
        sent += publish([env], secrets["demo-uav"], host, port)
    manifest = {
        "dataset": str(data),
        "speed": speed,
        "source_start": source_begin.isoformat(),
        "wall_start": wall_begin.isoformat(),
        "finished_at": now().isoformat(),
        "messages": sent,
        "distinct_observations": len(samples),
        "mode": "controlled_simulation_replay",
        "latency_basis": "actual local loopback; source science times are original",
    }
    (output / "publisher.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path)
    p.add_argument("--generate", choices=["healthy", "geometry", "thermal", "critical"])
    p.add_argument("--seed", type=int, default=8100)
    p.add_argument("--fidelity", choices=["L1", "L2"], default="L1")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--speed", type=float, default=20)
    p.add_argument("--no-inspections", action="store_true")
    p.add_argument("--duplicates", action="store_true")
    p.add_argument("--reverse", action="store_true")
    p.add_argument("--limit", type=int)
    p.add_argument("--step", action="store_true")
    p.add_argument("--control-file", type=Path)
    a = p.parse_args()
    data = a.dataset or generate(
        ROOT / "experiments/outputs" / ("phase5-data-" + str(a.seed)),
        a.seed,
        a.generate or "healthy",
        a.fidelity,
    )
    stream(
        data,
        a.output,
        speed=a.speed,
        inspections=not a.no_inspections,
        duplicates=a.duplicates,
        reverse=a.reverse,
        limit=a.limit,
        step=a.step,
        control_file=a.control_file,
    )
