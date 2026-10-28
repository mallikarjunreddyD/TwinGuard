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
from edge_demo import stream
from playwright.sync_api import sync_playwright


def save(p, v):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, indent=2, default=str) + "\n")


def stamp(v):
    return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()


def main(out):
    out.mkdir(parents=True, exist_ok=False)
    secrets = json.loads(Path(".edge/secrets.json").read_text())
    db = engine(
        "postgresql+psycopg://twinguard:" + secrets["database"] + "@localhost:18782/twinguard"
    )
    result = {
        "started_at": now().isoformat(),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "scope": "Focused correction test, not a repeat of all E4 fault/resource profiles. Same public pressure datasets 8210-8212; one ordinary backlog injected first. No policy/model changes.",
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
            page.goto("http://localhost:18780")
            page.get_by_label("Access token").fill(secrets["operator"])
            page.get_by_role("button", name="Open operations console").click()
            page.wait_for_function(
                "document.querySelector('[data-testid=asset-severity]')?.textContent==='RED'",
                timeout=180000,
            )
            browser_data["red_visible_at"] = now().isoformat()
            page.screenshot(path=str(out / "priority_red_browser.png"), full_page=True)
            while not stop.is_set():
                page.wait_for_timeout(250)
            b.close()

    t = threading.Thread(target=observe, daemon=True)
    t.start()
    stream(
        Path("experiments/outputs/e4-public-8220"),
        out / "ordinary-backlog",
        speed=80,
        inspections=False,
    )
    with db.connect() as c:
        result["ordinary_backlog_before_critical"] = c.execute(
            select(func.count()).select_from(jobs).where(jobs.c.status == "pending")
        ).scalar_one()
    for seed in [8210, 8211, 8212]:
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
            or not any(f"e4-public-{n}" in o["id"] for n in [8210, 8211, 8212])
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
    main(a.output)
