"""Loopback PostgreSQL/MQTT/API/browser validation; never physical authorization."""

from pathlib import Path
from datetime import datetime
import json
import time
import uuid
import threading
import httpx
import numpy as np
from sqlalchemy import select, func
from playwright.sync_api import sync_playwright
from twinguard.edge.storage import engine, records, observations, jobs
from twinguard.edge.contracts import Envelope, now
from twinguard.edge.protocols import publish
from twinguard.core.contracts import SensorObservation

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/outputs/phase6-platform"
URL = "http://localhost:18880/api/v1"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str) + "\n")


def stamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def main():
    OUT.mkdir(exist_ok=False)
    secrets = json.loads((ROOT / ".edge/secrets.json").read_text())
    db = engine(
        "postgresql+psycopg://twinguard:" + secrets["database"] + "@localhost:18882/twinguard"
    )
    headers = {"Authorization": "Bearer " + secrets["operator"]}
    client = httpx.Client(timeout=30)
    results = {
        "scope": "Short local-loopback comparison; not the complete corrected E4 or hardware commissioning",
        "started_at": now().isoformat(),
        "checks": {},
    }
    with db.connect() as c:
        results["database_bytes_before"] = c.execute(
            select(func.pg_database_size("twinguard"))
        ).scalar_one()
    path = ROOT / "experiments/outputs/e4-public-8210/observations/iot/observations.jsonl"
    template = next(
        SensorObservation.model_validate_json(line)
        for line in path.read_text().splitlines()
        if json.loads(line)["sensor_id"] == "pressure-01"
        and json.loads(line)["quality"] == "good"
        and json.loads(line)["value"] > 1150000
    )

    def pressure(label, count=30):
        ids = []
        epoch = "p6-" + uuid.uuid4().hex
        for index in range(count):
            ident = f"{epoch}-{index}"
            obs = template.model_copy(update={"observation_id": ident})
            at = now()
            env = Envelope(
                message_id="message-" + ident,
                source_id="demo-iot",
                sequence=index,
                sequence_epoch=epoch,
                emitted_at=at,
                provenance_id=obs.provenance_id,
                mode="simulation_replay",
                replay_acquired_at=at,
                observation=obs,
            )
            publish([env], secrets["demo-iot"], host="localhost", port=18883)
            ids.append(ident)
            time.sleep(0.15)
        deadline = time.monotonic() + 90
        timings = {}
        while time.monotonic() < deadline:
            with db.connect() as c:
                timings = {
                    r["job_id"]: r
                    for r in c.execute(
                        select(records.c.body).where(
                            records.c.kind == "timing", records.c.id.in_(ids)
                        )
                    ).scalars()
                }
            if len(timings) == count and all(
                "advisory_commit_confirmed_at" in v for v in timings.values()
            ):
                break
            time.sleep(0.1)
        if len(timings) != count:
            raise RuntimeError(f"{label}: completed {len(timings)}/{count}")
        details = []
        with db.connect() as c:
            for row in c.execute(select(observations).where(observations.c.id.in_(ids))).mappings():
                t = timings[row["id"]]
                traces = list(
                    c.execute(
                        select(records.c.body).where(
                            records.c.kind == "trace", records.c.id.in_(t["assessments"])
                        )
                    ).scalars()
                )
                trace = next(v for v in traces if v["assessment"]["asset_id"] == "BW-01")
                temporal = [
                    v["status"]
                    for v in trace["temporal"]
                    if v["evidence_id"] == "limit-" + row["id"]
                    and v["hazard_id"] == "critical-pressure"
                ]
                details.append(
                    {
                        "id": row["id"],
                        "receipt_to_commit_s": stamp(t["advisory_commit_confirmed_at"])
                        - stamp(row["received"]),
                        "temporal": temporal,
                        "severity": trace["assessment"]["severity"],
                    }
                )
        values = [d["receipt_to_commit_s"] for d in details]
        return {
            "label": label,
            "n": len(details),
            "current": sum("current" in d["temporal"] for d in details),
            "red": sum(d["severity"] == "red" for d in details),
            "p50_s": float(np.quantile(values, 0.5)),
            "p95_s": float(np.quantile(values, 0.95)),
            "max_s": max(values),
            "records": details,
        }

    results["idle"] = pressure("No planning jobs")
    save(OUT / "progress.json", results)
    stop = threading.Event()
    submitted = []
    errors = []

    def load():
        while not stop.is_set():
            try:
                ident = "load-" + uuid.uuid4().hex
                response = client.post(
                    URL + "/inspection-plans",
                    headers=headers,
                    json={"request_id": ident, "budget_views": 2, "budget_s": 70},
                )
                if response.status_code == 202:
                    submitted.append(ident)
                elif response.status_code != 409:
                    errors.append(str(response.status_code))
            except Exception as exc:
                errors.append(type(exc).__name__)
            time.sleep(0.1)

    thread = threading.Thread(target=load, daemon=True)
    thread.start()
    time.sleep(1)
    try:
        results["planning_loaded"] = pressure("Concurrent bounded planning workload")
    finally:
        stop.set()
        thread.join(5)
    results["planning_requests"] = len(submitted)
    results["load_errors"] = errors
    save(OUT / "progress.json", results)
    deadline = time.monotonic() + 180
    pending = -1
    while time.monotonic() < deadline:
        with db.connect() as c:
            pending = c.execute(
                select(func.count())
                .select_from(jobs)
                .where(jobs.c.kind == "planning", jobs.c.status.in_(["pending", "processing"]))
            ).scalar_one()
        if not pending:
            break
        time.sleep(0.5)
    results["planning_pending_at_end"] = pending
    history = client.get(URL + "/inspection-plans?limit=100", headers=headers).json()
    if not history:
        raise RuntimeError("No completed planning jobs")
    checks = results["checks"]
    checks["anonymous_rejected"] = client.get(URL + "/inspection-plans").status_code == 401
    viewer = {"Authorization": "Bearer " + secrets["viewer"]}
    checks["viewer_creation_rejected"] = (
        client.post(
            URL + "/inspection-plans", headers=viewer, json={"request_id": "unauthorized"}
        ).status_code
        == 403
    )
    plan = client.get(URL + "/inspection-plans/" + history[0]["plan_id"], headers=headers).json()
    checks["critical_context_preserved"] = any(
        v["access"] == "review_required" for v in plan["priorities"]
    )
    review_url = URL + "/inspection-plans/" + plan["plan_id"] + "/review"
    checks["critical_review_requires_ack"] = (
        client.post(
            review_url,
            headers=headers,
            json={"decision": "approved_for_simulation", "rationale": "reviewed safety context"},
        ).status_code
        == 422
    )
    checks["operator_simulation_review"] = (
        client.post(
            review_url,
            headers=headers,
            json={
                "decision": "approved_for_simulation",
                "rationale": "Explicitly reviewed critical-process restrictions and simulation-only scope",
                "acknowledges_critical_process": True,
            },
        ).status_code
        == 200
    )
    body = {"request_id": "duplicate-" + uuid.uuid4().hex, "budget_views": 2, "budget_s": 70}
    a = client.post(URL + "/inspection-plans", headers=headers, json=body)
    b = client.post(URL + "/inspection-plans", headers=headers, json=body)
    checks["duplicate_same_hash"] = (
        a.status_code == b.status_code == 202
        and a.json()["request_hash"] == b.json()["request_hash"]
    )
    checks["conflicting_duplicate_rejected"] = (
        client.post(
            URL + "/inspection-plans", headers=headers, json={**body, "budget_views": 3}
        ).status_code
        == 409
    )
    js_errors = []
    external = []
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
        page = browser.new_page(viewport={"width": 1700, "height": 1200})
        page.on("pageerror", lambda e: js_errors.append(str(e)))
        page.on(
            "request",
            lambda r: (
                external.append(r.url)
                if not r.url.startswith(("http://localhost:18880", "blob:", "data:"))
                else None
            ),
        )
        page.goto("http://localhost:18880")
        page.get_by_label("Access token").fill(secrets["operator"])
        page.get_by_role("button", name="Open operations console").click()
        page.get_by_role("button", name="Inspection Planning", exact=True).click()
        page.get_by_test_id("inspection-planner").wait_for()
        page.wait_for_function(
            "document.querySelector('[data-model-loaded=true]')!==null", timeout=60000
        )
        page.get_by_text("Asset need and access restrictions", exact=True).wait_for()
        page.screenshot(path=str(OUT / "E5-10-dashboard.png"), full_page=True)
        checks["browser_plan_rendered"] = page.get_by_text(
            "Asset need and access restrictions", exact=True
        ).is_visible()
        checks["browser_prediction_label"] = page.get_by_text(
            "Predicted coverage is not measured evidence. No physical UAV control.", exact=True
        ).is_visible()
        browser.close()
    results["browser"] = {"javascript_errors": js_errors, "external_requests": external}
    with db.connect() as c:
        results["database_bytes_after"] = c.execute(
            select(func.pg_database_size("twinguard"))
        ).scalar_one()
        results["planning_jobs"] = [
            dict(r) for r in c.execute(select(jobs).where(jobs.c.kind == "planning")).mappings()
        ]
    results["finished_at"] = now().isoformat()
    save(OUT / "report.json", results)
    print(
        {k: v for k, v in results.items() if k not in ("planning_jobs", "idle", "planning_loaded")},
        flush=True,
    )


if __name__ == "__main__":
    main()
