"""Targeted correction validation; original formal results/seal remain immutable."""

import argparse
import json
import subprocess
import time
from pathlib import Path
from sqlalchemy import select, func
from twinguard.edge.storage import engine, observations, jobs, records, inbox, stream as outbox
from twinguard.edge.contracts import now, Envelope
from twinguard.edge.protocols import publish
from twinguard.core.observations import load_public_observations
from twinguard.core.contracts import SensorObservation
from edge_demo import generate, stream
from edge_browser import run as browser

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    str(ROOT / ".edge/runtime.env"),
    "-p",
    "twinguard-e4-final",
    "-f",
    str(ROOT / "deployment/compose.yaml"),
    "-f",
    str(ROOT / "deployment/edge/compose.validation.yaml"),
]


def save(p, v):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, indent=2, default=str, allow_nan=False) + "\n")


def cmd(*a):
    return subprocess.run(COMPOSE + list(a), check=True, capture_output=True, text=True).stdout


def main(output):
    output.mkdir(parents=True, exist_ok=False)
    s = json.loads((ROOT / ".edge/secrets.json").read_text())
    db = engine("postgresql+psycopg://twinguard:" + s["database"] + "@localhost:18782/twinguard")
    report = {
        "started_at": now().isoformat(),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "original_run": str(ROOT / "experiments/outputs/phase5-E4-validated"),
        "corrections": [
            "OPC UA immutable DataValue constructor",
            "Open3D native shared libraries",
            "Inspection-history selection/current-frame/residual presentation",
        ],
        "scope": "No changes to observed values, models, thresholds or F1. Failed original subprofiles retained.",
        "steady_inspections": [],
    }
    for seed, kind, fidelity in [
        (8260, "geometry", "L1"),
        (8261, "thermal", "L1"),
        (8262, "geometry", "L2"),
    ]:
        path = ROOT / "experiments/outputs" / f"e4-corrected-public-{seed}"
        if not path.exists():
            generate(path, seed, kind, fidelity)
        started = now()
        stream(path, output / f"corrected-{seed}", speed=10, inspections=True)
        for _ in range(480):
            with db.connect() as c:
                pending = c.execute(
                    select(func.count())
                    .select_from(jobs)
                    .where(jobs.c.status.in_(["pending", "processing"]))
                ).scalar_one()
            if not pending:
                break
            time.sleep(0.5)
        report["steady_inspections"].append(
            {"seed": seed, "started_at": started.isoformat(), "finished_at": now().isoformat()}
        )
        print("Corrected steady profile", seed, "complete", flush=True)
    cmd(
        "--profile",
        "demo-opcua",
        "up",
        "-d",
        "--no-build",
        "--no-deps",
        "opcua-simulator",
        "opcua-adapter",
    )
    time.sleep(5)
    with db.connect() as c:
        before = list(
            c.execute(select(records.c.body).where(records.c.kind == "opcua_status")).scalars()
        )
    report["opcua_before"] = before
    stopped = now()
    cmd("stop", "-t", "1", "opcua-simulator")
    time.sleep(3)
    cmd("start", "opcua-simulator")
    for _ in range(30):
        time.sleep(1)
        with db.connect() as c:
            after = list(
                c.execute(select(records.c.body).where(records.c.kind == "opcua_status")).scalars()
            )
        if after and max(r["at"] for r in after) > stopped.isoformat():
            break
    report["opcua_after"] = after
    report["opcua_recovered"] = bool(after and max(r["at"] for r in after) > stopped.isoformat())
    code = """import asyncio,json
from asyncua import Client,ua
async def main():
 async with Client('opc.tcp://opcua-simulator:4840/twinguard/') as c:
  idx=await c.get_namespace_index('urn:twinguard:measured')
  node=c.get_node(ua.NodeId('pressure-01',idx))
  value=await node.read_value()
  unit=await c.get_node(ua.NodeId('pressure-01.Unit',idx)).read_value()
  result={'numeric_read':isinstance(value,(int,float)),'unit':unit}
  try:
   await node.write_value(123.0)
   result['write_rejected']=False
  except Exception as e:
   result['write_rejected']=True
   result['write_error']=type(e).__name__
  print(json.dumps(result))
asyncio.run(main())"""
    report["opcua_read_only"] = json.loads(cmd("exec", "-T", "api", "python", "-c", code).strip())
    original = next(
        r
        for r in load_public_observations(ROOT / ".edge/opcua-public")
        if isinstance(r, SensorObservation) and r.sensor_id == "pressure-01"
    )
    with db.connect() as c:
        before_count = c.execute(
            select(func.count())
            .select_from(observations)
            .where(observations.c.id == original.observation_id)
        ).scalar_one()
    env = Envelope(
        message_id="cross-protocol-lineage-test",
        source_id="demo-iot",
        sequence=999999,
        emitted_at=now(),
        mode="simulation_replay",
        replay_acquired_at=now(),
        observation=original,
        provenance_id=original.provenance_id,
    )
    publish([env], s["demo-iot"], "localhost", 18783)
    time.sleep(2)
    with db.connect() as c:
        after_count = c.execute(
            select(func.count())
            .select_from(observations)
            .where(observations.c.id == original.observation_id)
        ).scalar_one()
        job_count = c.execute(
            select(func.count()).select_from(jobs).where(jobs.c.id == original.observation_id)
        ).scalar_one()
    report["cross_protocol_lineage"] = {
        "before": before_count,
        "after": after_count,
        "jobs": job_count,
    }
    report["browser"] = browser(output / "browser")
    report["finished_at"] = now().isoformat()
    with db.connect() as c:
        for name, table in [
            ("observations", observations),
            ("jobs", jobs),
            ("inbox", inbox),
            ("records", records),
            ("stream", outbox),
        ]:
            save(output / f"{name}.json", [dict(r) for r in c.execute(select(table)).mappings()])
        report["job_counts"] = dict(
            c.execute(select(jobs.c.status, func.count()).group_by(jobs.c.status)).all()
        )
    report["images"] = {
        service: subprocess.check_output(
            ["docker", "inspect", "twinguard-e4-final-" + service + "-1", "--format", "{{.Image}}"],
            text=True,
        ).strip()
        for service in [
            "api",
            "fast-worker",
            "inspection-worker",
            "frontend",
            "broker",
            "database",
            "opcua-simulator",
            "opcua-adapter",
        ]
    }
    save(output / "report.json", report)
    import hashlib

    save(
        output / "predictions_ready.json",
        {
            "finished_at": now().isoformat(),
            "artifacts": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in output.glob("*.json")
                if p.name != "predictions_ready.json"
            },
        },
    )
    print("Corrected integration report saved", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    main(a.output)
