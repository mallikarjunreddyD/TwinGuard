"""Measured local E4 controller. No labels enter deployed services. Results never overwrite."""

from functools import partial
import argparse
import json
import os
import platform
import subprocess
import threading
import time
from pathlib import Path
from datetime import datetime
import httpx
import numpy as np
from sqlalchemy import select, func, text
from twinguard.edge.contracts import now, Envelope
from twinguard.edge.storage import engine, observations, records, jobs, inbox, stream as outbox
from twinguard.edge.protocols import mqtt_client
from twinguard.edge.ingestion import topic
from twinguard.core.observations import load_public_observations
from twinguard.core.contracts import SensorObservation
from edge_demo import generate, stream

ROOT = Path(__file__).resolve().parents[1]
os.environ["TWINGUARD_PORT"] = "19080"

stream = partial(stream, url="http://localhost:19080", port=19083)
COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    str(ROOT / ".edge/runtime.env"),
    "-p",
    "twinguard-phase7-corrected",
    "-f",
    str(ROOT / "deployment/compose.yaml"),
    "-f",
    str(ROOT / "deployment/edge/compose.phase7-corrected-validation.yaml"),
]
URL = "http://localhost:19080"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str, allow_nan=False) + "\n")


def command(*args):
    return subprocess.run(COMPOSE + list(args), check=True, capture_output=True, text=True).stdout


def percentiles(values):
    if not values:
        return {"n": 0, "p50": None, "p95": None, "p99": None, "max": None}
    return {
        "n": len(values),
        **{
            key: float(np.percentile(values, p))
            for key, p in [("p50", 50), ("p95", 95), ("p99", 99)]
        },
        "max": max(values),
    }


def main(output, smoke=False, project="twinguard-phase7-corrected"):
    COMPOSE[5] = project
    output.mkdir(parents=True, exist_ok=False)
    secrets = json.loads((ROOT / ".edge/secrets.json").read_text())
    headers = {"Authorization": "Bearer " + secrets["operator"]}
    db = engine(
        "postgresql+psycopg://twinguard:" + secrets["database"] + "@127.0.0.1:19082/twinguard"
    )
    began = now()
    report = {
        "experiment": "Phase7-full-E4-recovery-retest",
        "status": "running",
        "started_at": began.isoformat(),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "mode": "actual CPU software-loopback; no hardware/field latency claim",
        "profiles": [],
        "retest_rationale": "Preserve failed first full attempt. Fresh DB, same E4 profiles and concurrent planning; bounded drain deadline 900s to observe actual recovery under measured CPU contention. This does not change 10s critical TTL or establish timely critical interpretation.",
        "host": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
        },
        "failures": [],
        "samples": [],
    }
    stop = threading.Event()

    def monitor():
        while not stop.is_set():
            sample = {"at": now().isoformat()}
            try:
                t = time.perf_counter()
                with db.connect() as c:
                    c.execute(text("SELECT 1"))
                    sample["database_latency_s"] = time.perf_counter() - t
                    sample["queue"] = dict(
                        c.execute(select(jobs.c.status, func.count()).group_by(jobs.c.status)).all()
                    )
                    sample["db_bytes"] = c.execute(
                        text("SELECT pg_database_size(current_database())")
                    ).scalar_one()
                t = time.perf_counter()
                r = httpx.get(URL + "/api/v1/platform/health", headers=headers, timeout=10)
                sample["api_latency_s"] = time.perf_counter() - t
                sample["api_status"] = r.status_code
                result = subprocess.run(
                    ["docker", "stats", "--no-stream", "--format", "{{json .}}"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                sample["containers"] = [
                    json.loads(x)
                    for x in result.stdout.splitlines()
                    if "twinguard-phase7-corrected" in x
                ]
            except Exception as exc:
                sample["error"] = str(exc)[:300]
            report["samples"].append(sample)
            stop.wait(1)

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    report["concurrent_planning"] = []

    def planning_load():
        import uuid

        while not stop.is_set():
            started = time.perf_counter()
            try:
                response = httpx.post(
                    URL + "/api/v1/inspection-plans",
                    headers=headers,
                    json={
                        "request_id": "p7-stress-" + uuid.uuid4().hex,
                        "method": "P3v2",
                        "budget_views": 2,
                        "budget_s": 70,
                    },
                    timeout=15,
                )
                report["concurrent_planning"].append(
                    {
                        "at": now().isoformat(),
                        "status": response.status_code,
                        "latency_s": time.perf_counter() - started,
                    }
                )
            except Exception as exc:
                report["concurrent_planning"].append(
                    {"at": now().isoformat(), "error": str(exc)[:200]}
                )
            stop.wait(10)

    planning_thread = threading.Thread(target=planning_load, daemon=True)
    planning_thread.start()
    browser_results = {}

    def observe_browser():
        from playwright.sync_api import sync_playwright

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--use-gl=angle",
                        "--use-angle=swiftshader",
                        "--enable-unsafe-swiftshader",
                    ],
                )
                page = browser.new_page(viewport={"width": 1500, "height": 1100})
                page.goto(URL)
                page.get_by_label("Access token").fill(secrets["operator"])
                page.get_by_role("button", name="Open operations console").click()
                page.wait_for_selector('[data-model-loaded="true"]', timeout=60000)
                page.wait_for_function(
                    "document.querySelector('[data-testid=asset-severity]')?.textContent==='RED'",
                    timeout=900000,
                )
                browser_results["first_red_visible_at"] = now().isoformat()
                page.screenshot(path=str(output / "first_red_browser.png"), full_page=True)
                browser_results["deliveries"] = []
                last_seq = 0
                while not stop.is_set():
                    page.wait_for_timeout(1000)
                    new = page.evaluate("(window.__tgDeliveries || [])")
                    browser_results["deliveries"].extend([r for r in new if r["seq"] > last_seq])
                    last_seq = max([r["seq"] for r in new] + [last_seq])
                browser_results["last_stream_id"] = page.evaluate("window.__tgLastStreamId")
                browser.close()
        except Exception as exc:
            browser_results["error"] = str(exc)

    browser_thread = threading.Thread(target=observe_browser, daemon=True)
    browser_thread.start()

    def drain(timeout=900):
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            with db.connect() as c:
                pending = c.execute(
                    select(func.count())
                    .select_from(jobs)
                    .where(jobs.c.status.in_(["pending", "processing"]))
                ).scalar_one()
            if pending == 0:
                return
            time.sleep(0.5)
        raise RuntimeError("Queue drain timed out")

    def trial(
        profile,
        seed,
        kind="healthy",
        speed=10,
        inspection=False,
        duplicates=False,
        reverse=False,
        limit=None,
    ):
        path = ROOT / "experiments/outputs" / f"e4-public-{seed}"
        if not path.exists():
            generate(path, seed, kind, "L2" if profile == "B6-L2" else "L1")
        started = now()
        result = stream(
            path,
            output / f"{profile}-{seed}",
            speed=speed,
            inspections=inspection,
            duplicates=duplicates,
            reverse=reverse,
            limit=limit,
        )
        drain()
        entry = {
            "profile": profile,
            "seed": seed,
            "dataset": str(path),
            "started": started.isoformat(),
            "finished": now().isoformat(),
            "published": len(result["messages"]),
            "distinct_published": result["distinct_observations"],
        }
        ids = {r["observation_id"] for r in result["messages"] if r.get("observation_id")}
        with db.connect() as c:
            entry["persisted"] = c.execute(
                select(func.count()).select_from(observations).where(observations.c.id.in_(ids))
            ).scalar_one()
        entry["completeness"] = entry["persisted"] / len(ids) if ids else None
        report["profiles"].append(entry)
        save(output / "progress.json", report)
        print("Completed", profile, seed, entry["persisted"], "/", len(ids), flush=True)
        return path

    try:
        # B0: same prior public evidence as the pre-platform reference, only computation timing.
        from twinguard.fusion.io import read_evidence
        from twinguard.fusion.engine import replay
        from twinguard.fusion.policies import load_policy, policy_hash

        source = ROOT / "output/phase4-replay"
        values = read_evidence(ROOT / "output/phase4-prepare")
        old = json.loads((source / "history.json").read_text())
        end = datetime.fromisoformat(old[-1]["assessment"]["assessed_at"].replace("Z", "+00:00"))
        p = load_policy(ROOT / "configs/fusion/hazards.yaml")
        start = time.perf_counter()
        state, history = replay(values, p, end)
        report["profiles"].append(
            {
                "profile": "B0",
                "runtime_s": time.perf_counter() - start,
                "assessments": len(history),
                "basis": "Offline computation only; not transport delay",
            }
        )
        report["policy_sha256"] = policy_hash(p)
        report["images"] = subprocess.check_output(
            ["docker", "images", "--format", "{{json .}}"], text=True
        ).splitlines()
        with db.connect() as c:
            report["database_schema"] = c.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            report["application_role_superuser"] = c.execute(
                text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")
            ).scalar_one()
        report["declared_acceptance"] = {
            "critical_ttl_s": 10,
            "scope": "Full original E4 profiles plus concurrent P3v2 planning; software loopback",
            "current_required_fraction": 1.0,
            "no_missing_committed_observations": True,
        }
        repeats = 1 if smoke else 3
        for i in range(repeats):
            trial(
                "B1", 8200 + i, speed=2 if i == 0 and not smoke else 10, limit=60 if smoke else None
            )
        # First red happens here, while a real browser and resource sampling run concurrently.
        for i in range(repeats):
            trial("B7", 8210 + i, kind="critical", speed=10, limit=None)
        trial("B2", 8220, speed=80)
        trial("B3", 8221, speed=30, duplicates=True, reverse=True)
        for name, service, seed in [
            ("B4", "fast-worker", 8230),
            ("B5", "broker", 8231),
            ("B4-api", "api", 8232),
            ("B4-database", "database", 8233),
        ]:
            path = ROOT / "experiments/outputs" / f"e4-public-{seed}"
            if not path.exists():
                generate(path, seed, "healthy")
            failures = []

            def deliver():
                try:
                    stream(path, output / name, speed=5, inspections=False)
                except Exception as exc:
                    failures.append(str(exc))

            worker = threading.Thread(target=deliver)
            worker.start()
            time.sleep(2)
            with db.connect() as c:
                committed_before = c.execute(
                    select(func.count()).select_from(observations)
                ).scalar_one()
                events_before = set(
                    c.execute(select(records.c.id).where(records.c.kind == "event")).scalars()
                )
            stopped = now()
            command("stop", "-t", "1", service)
            time.sleep(3)
            command("start", service)
            # Wait for authenticated API/database recovery, not just container start.
            ready = None
            for _ in range(90):
                try:
                    r = httpx.get(URL + "/api/v1/platform/health", headers=headers, timeout=2)
                    if r.status_code == 200 and r.json()["readiness"] == "ready":
                        ready = now()
                        break
                except Exception:
                    pass
                time.sleep(1)
            worker.join(120)
            drain()
            with db.connect() as c:
                count_after = c.execute(select(func.count()).select_from(observations)).scalar_one()
                events_after = set(
                    c.execute(select(records.c.id).where(records.c.kind == "event")).scalars()
                )
            report["profiles"].append(
                {
                    "profile": name,
                    "service": service,
                    "stop_requested": stopped.isoformat(),
                    "ready_at": ready.isoformat() if ready else None,
                    "recovery_s": (ready - stopped).total_seconds() if ready else None,
                    "committed_before": committed_before,
                    "committed_after": count_after,
                    "events_preserved": events_before <= events_after,
                    "publisher_errors": failures,
                }
            )
            save(output / "progress.json", report)
            print("Recovery", service, "complete", flush=True)
        # Optional real numeric OPC UA server + read-only adapter use original public sensing records.
        command(
            "--profile", "demo-opcua", "up", "-d", "--no-build", "opcua-simulator", "opcua-adapter"
        )
        time.sleep(8)
        with db.connect() as c:
            opc_status = list(
                c.execute(select(records.c.body).where(records.c.kind == "opcua_status")).scalars()
            )
            opc_count = c.execute(
                select(func.count())
                .select_from(observations)
                .where(observations.c.source == "opcua-demo")
            ).scalar_one()
        report["profiles"].append(
            {
                "profile": "B5-OPCUA",
                "node_statuses": opc_status,
                "distinct_observations": opc_count,
                "read_mode": "numeric channels with engineering units and original public-record lineage; polled snapshots, not every source update",
            }
        )
        command("stop", "-t", "1", "opcua-simulator")
        time.sleep(3)
        command("start", "opcua-simulator")
        time.sleep(5)
        with db.connect() as c:
            refreshed = list(
                c.execute(select(records.c.body).where(records.c.kind == "opcua_status")).scalars()
            )
        report["opcua_recovery"] = {
            "statuses_before": len(opc_status),
            "statuses_after": len(refreshed),
            "latest_status_at": max([r["at"] for r in refreshed], default=None),
        }
        command("stop", "-t", "1", "opcua-adapter", "opcua-simulator")
        # Quiescent sources become explicitly unavailable; no alert-free inference of health.
        time.sleep(16)
        monitoring = httpx.get(URL + "/api/v1/monitoring/health", headers=headers).json()
        report["profiles"].append({"profile": "B6", "monitoring": monitoring})
        trial("B8-geometry", 8240, kind="geometry", speed=10, inspection=True)
        trial("B8-thermal", 8241, kind="thermal", speed=10, inspection=True)
        trial("B6-L2", 8242, kind="geometry", speed=10, inspection=True)
        # Real protocol security checks, no fake broker substitutes.
        unauthorized = mqtt_client("demo-iot", "incorrect-" + str(time.time()), "unauthorized-test")
        result = []
        unauthorized.on_connect = lambda c, u, f, rc, p: result.append(str(rc))
        unauthorized.connect("localhost", 19083)
        unauthorized.loop_start()
        time.sleep(2)
        unauthorized.disconnect()
        unauthorized.loop_stop()
        report["unauthorized_connection_results"] = result
        # Correctly authenticated publisher attempts another source topic; broker must discard it.
        sample = next(
            r
            for r in load_public_observations(ROOT / "experiments/outputs/e4-public-8200")
            if isinstance(r, SensorObservation)
        )
        env = Envelope(
            message_id="acl-violation-e4",
            source_id="demo-uav",
            sequence=999999,
            emitted_at=now(),
            provenance_id=sample.provenance_id,
            observation=sample,
        )
        client = mqtt_client("demo-iot", secrets["demo-iot"], "acl-test")
        client.connect("localhost", 19083)
        client.loop_start()
        m = client.publish(topic("demo-uav"), env.model_dump_json(), qos=1)
        m.wait_for_publish(5)
        client.disconnect()
        client.loop_stop()
        time.sleep(1)
        with db.connect() as c:
            report["unauthorized_topic_persisted"] = c.execute(
                select(func.count()).select_from(inbox).where(inbox.c.id == "acl-violation-e4")
            ).scalar_one()
        from edge_browser import run

        report["browser"] = run(output / "browser", url=URL)
        report["profiles"].append({"profile": "B9", "checks": report["browser"]["checks"]})
        report["status"] = "executed"
    except Exception as exc:
        report["status"] = "failed"
        report["failures"].append(str(exc))
        print("E4 failure", str(exc), flush=True)
    finally:
        stop.set()
        thread.join(15)
        browser_thread.join(15)
        report["live_browser"] = browser_results
        report["finished_at"] = now().isoformat()
        report["elapsed_s"] = (now() - began).total_seconds()
        with db.connect() as c:
            # Public operational predictions/timestamps sealed before any optional evaluator truth access.
            for name, table in [
                ("observations", observations),
                ("jobs", jobs),
                ("inbox", inbox),
                ("records", records),
                ("stream", outbox),
            ]:
                rows = [dict(r) for r in c.execute(select(table)).mappings()]
                save(output / f"{name}.json", rows)
            report["jobs_final"] = dict(
                c.execute(select(jobs.c.status, func.count()).group_by(jobs.c.status)).all()
            )
        save(output / "report.json", report)
        import hashlib

        save(
            output / "predictions_ready.json",
            {
                "finished_at": now().isoformat(),
                "artifacts": {
                    p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(output.glob("*.json"))
                    if p.name != "predictions_ready.json"
                },
            },
        )
        print("E4", report["status"], report["elapsed_s"], "seconds", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--project", default="twinguard-phase7-corrected")
    args = p.parse_args()
    main(args.output, args.smoke, args.project)
