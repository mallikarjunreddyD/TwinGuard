"""Focused E4 correction: same public critical inputs under ordinary backlog."""

import argparse
import json
import subprocess
import threading
import time
from pathlib import Path
from datetime import datetime
from sqlalchemy import select, func
from twinguard.edge.contracts import now
from twinguard.edge.storage import engine, observations, jobs, records
from edge_demo import stream as original_stream, generate
from functools import partial

from playwright.sync_api import sync_playwright

stream = partial(original_stream, url="http://localhost:19180", port=19183)


def save(p, v):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, indent=2, default=str) + "\n")


def stamp(v):
    return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()


def main(out):
    out.mkdir(parents=True, exist_ok=False)
    secrets = json.loads(Path(".edge/secrets.json").read_text())
    db = engine(
        "postgresql+psycopg://twinguard:" + secrets["database"] + "@localhost:19182/twinguard"
    )
    result = {
        "started_at": now().isoformat(),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "scope": "Supplementary corrected 500-message backlog after the completed full E4; fresh critical streams overlap real LiDAR/thermal jobs and planning. Unique MQTT client IDs, unchanged measured-value models and 10s F1 TTL.",
        "datasets": [],
    }
    browser_data = {}
    stop = threading.Event()

    def observe():
        with sync_playwright() as p:
            b = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--use-gl=angle",
                    "--use-angle=swiftshader",
                    "--enable-unsafe-swiftshader",
                ],
            )
            page = b.new_page(viewport={"width": 1500, "height": 1100})
            page.goto("http://localhost:19180")
            page.get_by_label("Access token").fill(secrets["operator"])
            page.get_by_role("button", name="Open operations console").click()
            page.wait_for_function(
                "document.querySelector('[data-testid=asset-severity]')?.textContent==='RED'",
                timeout=186000,
            )
            browser_data["red_visible_at"] = now().isoformat()
            page.screenshot(path=str(out / "priority_red_browser.png"), full_page=True)
            while not stop.is_set():
                page.wait_for_timeout(250)
            b.close()

    t = threading.Thread(target=observe, daemon=True)
    t.start()
    for seed, kind in [
        (18600, "healthy"),
        (18601, "healthy"),
        (18610, "critical"),
        (18611, "critical"),
        (18612, "critical"),
    ]:
        path = Path("experiments/outputs") / f"e4-public-{seed}"
        if not path.exists():
            generate(path, seed, kind, "L1")
    subprocess.run(
        ["docker", "stop", "twinguard-phase7-admission-fast-worker-1"],
        check=True,
        capture_output=True,
    )
    ids = set()
    try:
        for seed, count in [(18600, 250), (18601, 250)]:
            part = out / f"ordinary-{seed}"
            stream(
                Path("experiments/outputs") / f"e4-public-{seed}",
                part,
                speed=10000,
                inspections=False,
                limit=count,
            )
            manifest = json.loads((part / "publisher.json").read_text())
            ids.update(m["observation_id"] for m in manifest["messages"] if m.get("observation_id"))
        for _ in range(300):
            with db.connect() as c:
                pending = c.execute(
                    select(func.count()).select_from(jobs).where(jobs.c.status == "pending")
                ).scalar_one()
            if pending >= 500:
                break
            time.sleep(0.1)
        result["measured_paused_backlog"] = pending
    finally:
        subprocess.run(
            ["docker", "start", "twinguard-phase7-admission-fast-worker-1"],
            check=True,
            capture_output=True,
        )
    for _ in range(600):
        with db.connect() as c:
            persisted = c.execute(
                select(func.count()).select_from(observations).where(observations.c.id.in_(ids))
            ).scalar_one()
        if persisted == len(ids):
            break
        time.sleep(0.1)
    if persisted != len(ids):
        raise RuntimeError("Ordinary input did not reach durable storage")
    result["ordinary_ingestion_confirmed_at"] = now().isoformat()
    with db.connect() as c:
        result["ordinary_backlog_before_critical"] = c.execute(
            select(func.count()).select_from(jobs).where(jobs.c.status == "pending")
        ).scalar_one()
    from concurrent.futures import ThreadPoolExecutor
    import httpx
    import uuid

    for seed, kind in [(18700, "geometry"), (18701, "thermal")]:
        data = Path("experiments/outputs") / f"e4-public-{seed}"
        if not data.exists():
            generate(data, seed, kind, "L1")
    heavy = ThreadPoolExecutor(max_workers=2)
    futures = [
        heavy.submit(
            stream,
            Path("experiments/outputs") / f"e4-public-{seed}",
            out / f"mixed-inspection-{seed}",
            speed=10,
            inspections=True,
            limit=1,
        )
        for seed in (18700, 18701)
    ]
    result["concurrent_planning"] = []

    def planning():
        while not stop.is_set():
            t0 = time.perf_counter()
            try:
                response = httpx.post(
                    "http://localhost:19180/api/v1/inspection-plans",
                    headers={"Authorization": "Bearer " + secrets["operator"]},
                    json={
                        "request_id": "p7-final-mixed-" + uuid.uuid4().hex,
                        "method": "P3v2",
                        "budget_views": 2,
                        "budget_s": 70,
                    },
                    timeout=15,
                )
                result["concurrent_planning"].append(
                    {
                        "at": now().isoformat(),
                        "status": response.status_code,
                        "latency_s": time.perf_counter() - t0,
                    }
                )
            except Exception as exc:
                result["concurrent_planning"].append(
                    {"at": now().isoformat(), "error": str(exc)[:150]}
                )
            stop.wait(5)

    planner = threading.Thread(target=planning, daemon=True)
    planner.start()
    for seed in [18610, 18611, 18612]:
        started = now()
        stream(
            Path("experiments/outputs") / f"e4-public-{seed}",
            out / f"critical-{seed}",
            speed=10,
            inspections=False,
        )
        # Keep backlog during first critical stream; subsequent streams start after a drain.
        for _ in range(600):
            with db.connect() as c:
                pending = c.execute(
                    select(func.count())
                    .select_from(jobs)
                    .where(jobs.c.status.in_(["pending", "processing"]))
                ).scalar_one()
            if not pending:
                break
            time.sleep(0.25)
        result["datasets"].append(
            {"seed": seed, "started_at": started.isoformat(), "finished_at": now().isoformat()}
        )
        print("Priority stream", seed, "complete", flush=True)
    result["concurrent_inspection_publishers"] = [f.result() for f in futures]
    heavy.shutdown()
    with db.connect() as c:
        obs = [dict(r) for r in c.execute(select(observations)).mappings()]
        rec = [dict(r) for r in c.execute(select(records)).mappings()]
        jobrows = [dict(r) for r in c.execute(select(jobs)).mappings()]
    traces = {r["id"]: r["body"] for r in rec if r["kind"] == "trace"}
    timing = {r["id"]: r["body"] for r in rec if r["kind"] == "timing"}
    critical = []
    for o in obs:
        if (
            o["sensor"] != "pressure-01"
            or o["body"]["quality"] != "good"
            or o["body"]["value"] < 1150000
            or not any(f"e4-public-{n}" in o["id"] for n in [18610, 18611, 18612])
        ):
            continue
        item = timing[o["id"]]
        trace = next(
            traces[i] for i in item["assessments"] if traces[i]["assessment"]["asset_id"] == "BW-01"
        )
        states = [
            d["status"]
            for d in trace["temporal"]
            if d["evidence_id"] == "limit-" + o["id"] and d["hazard_id"] == "critical-pressure"
        ]
        critical.append(
            {
                "observation_id": o["id"],
                "received": o["received"],
                "state": states,
                "receipt_to_advisory_s": stamp(item["advisory_commit_confirmed_at"])
                - stamp(o["received"]),
                "assessment_severity": trace["assessment"]["severity"],
                "priority": o["metadata"]["scheduling_priority"],
            }
        )
    result["critical_readings"] = critical
    result["job_statuses"] = {
        s: sum(j["status"] == s for j in jobrows)
        for s in ["completed", "failed", "pending", "processing"]
    }
    result["finished_at"] = now().isoformat()
    stop.set()
    planner.join(20)
    t.join(10)
    result["browser"] = browser_data
    save(out / "report.json", result)
    save(out / "observations.json", obs)
    save(out / "records.json", rec)
    save(out / "jobs.json", jobrows)
    import hashlib

    save(
        out / "predictions_ready.json",
        {
            "at": now().isoformat(),
            "artifacts": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in out.glob("*.json")
                if p.name != "predictions_ready.json"
            },
        },
    )
    from collections import Counter

    print(
        "Critical temporal states",
        dict(Counter(s for r in critical for s in r["state"])),
        flush=True,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    try:
        main(a.output)
    except Exception as exc:
        a.output.mkdir(parents=True, exist_ok=True)
        save(
            a.output / "incomplete_run.json",
            {
                "status": "incomplete",
                "error": type(exc).__name__ + ": " + str(exc),
                "scope": "No unexecuted trial marked successful; partial publishers and artifacts retained",
            },
        )
        raise
