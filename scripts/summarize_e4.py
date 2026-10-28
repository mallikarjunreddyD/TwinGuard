"""Read-only E4 audit, measured figures and compact reproducibility evidence."""

import argparse
import hashlib
import importlib.metadata
import json
import platform
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]


def read(p):
    return json.loads(p.read_text())


def save(p, v):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, indent=2, default=str, allow_nan=False) + "\n")


def stamp(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def stats(a):
    a = [v for v in a if v is not None]
    return {
        "n": len(a),
        **{f"p{p}": float(np.percentile(a, p)) if a else None for p in [50, 95, 99]},
        "max": max(a) if a else None,
    }


def run(directory):
    seal = read(directory / "predictions_ready.json")
    for name, digest in seal["artifacts"].items():
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest, name
    r = read(directory / "report.json")
    obs = read(directory / "observations.json")
    jobs = read(directory / "jobs.json")
    records = read(directory / "records.json")
    observations = {o["id"]: o for o in obs}
    timings = {o["id"]: o["body"] for o in records if o["kind"] == "timing"}
    analyses = {o["id"]: o["body"] for o in records if o["kind"] == "analysis"}
    latencies = {
        k: []
        for k in [
            "publisher_to_receipt",
            "receipt_to_ingest_commit_observed",
            "receipt_to_job_start",
            "iot_receipt_to_advisory_commit",
            "inspection_receipt_to_advisory_commit",
            "analytics_iot",
            "analytics_inspection",
            "fusion_and_commit_iot",
            "fusion_and_commit_inspection",
        ]
    }
    timeline = []
    for ident, o in observations.items():
        meta = o["metadata"]
        timing = timings.get(ident)
        recv = stamp(o["received"])
        if meta.get("publisher_emitted_at"):
            latencies["publisher_to_receipt"].append(recv - stamp(meta["publisher_emitted_at"]))
        if meta.get("ingest_commit_confirmed_at"):
            latencies["receipt_to_ingest_commit_observed"].append(
                stamp(meta["ingest_commit_confirmed_at"]) - recv
            )
        if timing:
            start = stamp(timing["job_start"])
            done = stamp(timing["analytics_complete"])
            committed = stamp(
                timing.get("advisory_commit_confirmed_at", timing["advisory_available"])
            )
            latencies["receipt_to_job_start"].append(start - recv)
            latencies["iot_receipt_to_advisory_commit"].append(committed - recv)
            latencies["analytics_iot"].append(done - start)
            latencies["fusion_and_commit_iot"].append(committed - done)
            timeline.append(
                {"observation_id": ident, "sensor": o["sensor"], "receipt": o["received"], **timing}
            )
    for job in jobs:
        if job["kind"] == "inspection" and job["id"] in timings:
            timing = timings[job["id"]]
            received = stamp(job["body"]["received"])
            start = stamp(timing["job_start"])
            done = stamp(timing["analytics_complete"])
            committed = stamp(
                timing.get("advisory_commit_confirmed_at", timing["advisory_available"])
            )
            latencies["inspection_receipt_to_advisory_commit"].append(committed - received)
            latencies["analytics_inspection"].append(done - start)
            latencies["fusion_and_commit_inspection"].append(committed - done)
    publishers = []
    for file in sorted(directory.rglob("publisher.json")):
        value = read(file)
        ids = {m["observation_id"] for m in value["messages"] if m.get("observation_id")}
        persisted = len(ids & set(observations))
        publishers.append(
            {
                "run": str(file.parent.relative_to(directory)),
                "published_messages": len(value["messages"]),
                "distinct_observations": len(ids),
                "persisted": persisted,
                "missing": len(ids) - persisted,
                "completeness": persisted / len(ids) if ids else None,
                "elapsed_s": stamp(value["finished_at"]) - stamp(value["wall_start"]),
            }
        )
    audits = [o["body"] for o in records if o["kind"] == "audit"]
    notices = [o["body"] for o in records if o["kind"] == "notice"]
    opens = Counter(
        (n["event_id"], n["transition"])
        for n in notices
        if n["transition"] in ["opened", "escalated"]
    )
    resource = r["samples"]
    dbtimes = [s["database_latency_s"] for s in resource if "database_latency_s" in s]
    apitimes = [s["api_latency_s"] for s in resource if "api_latency_s" in s]
    deliveries = r.get("live_browser", {}).get("deliveries", [])
    browser_job = []
    for delivery in deliveries:
        server = delivery.get("server", {})
        body = server.get("body", {})
        if server.get("kind") == "job_completed" and body.get("job_id") in timings:
            t = timings[body["job_id"]]
            browser_job.append(
                delivery["wall_ms"] / 1000
                - stamp(t.get("advisory_commit_confirmed_at", t["advisory_available"]))
            )
    red_candidates = []
    for row in timeline:
        o = observations[row["observation_id"]]
        if (
            o["sensor"] == "pressure-01"
            and float(o["body"]["value"]) >= 1150000
            and "e4-public-8210" in o["id"]
        ):
            red_candidates.append(row)
    first = min(red_candidates, key=lambda x: x["receipt"]) if red_candidates else None
    browser_first = r.get("live_browser", {}).get("first_red_visible_at")
    summaries = {
        "experiment": "E4",
        "status": r["status"],
        "source_commit": r["source_commit"],
        "started_at": r["started_at"],
        "finished_at": r["finished_at"],
        "elapsed_s": r["elapsed_s"],
        "policy_sha256": r.get("policy_sha256"),
        "database_schema": r.get("database_schema"),
        "application_role_superuser": r.get("application_role_superuser"),
        "profiles": r["profiles"],
        "publisher_completeness": publishers,
        "latency_s": {k: stats(v) for k, v in latencies.items()},
        "database_query_s": stats(dbtimes),
        "api_response_s": stats(apitimes),
        "browser_commit_to_sse_receipt_s": stats(browser_job),
        "first_critical": {
            "record": first,
            "browser_visible_at": browser_first,
            "receipt_to_browser_visible_s": stamp(browser_first) - stamp(first["receipt"])
            if first and browser_first
            else None,
        },
        "audit_counts": dict(Counter(a["reason"] for a in audits)),
        "duplicate_durable_observation_ids": len(obs) - len(observations),
        "repeated_event_open_effects": sum(n - 1 for n in opens.values() if n > 1),
        "job_status_counts": dict(Counter(j["status"] for j in jobs)),
        "retried_jobs": sum(j["attempts"] > 1 for j in jobs),
        "failed_jobs": [j for j in jobs if j["status"] == "failed"],
        "inspections": [
            {
                "id": k,
                "geometric_statuses": [g["status"] for g in v.get("geometric", [])],
                "geometry_regions": sum(len(g["regions"]) for g in v.get("geometric", [])),
                "thermal_statuses": [t["status"] for t in v.get("thermal", [])],
                "thermal_regions": sum(len(t["regions"]) for t in v.get("thermal", [])),
            }
            for k, v in analyses.items()
            if v.get("kind") == "inspection"
        ],
        "browser": r.get("browser"),
        "live_browser": {k: v for k, v in r.get("live_browser", {}).items() if k != "deliveries"},
        "security": {
            "unauthorized_connection_results": r.get("unauthorized_connection_results"),
            "unauthorized_topic_persisted": r.get("unauthorized_topic_persisted"),
        },
        "environment": r["host"],
        "resource_samples": len(resource),
        "peak_database_bytes": max([s.get("db_bytes", 0) for s in resource] + [0]),
        "software": {
            n: importlib.metadata.version(n)
            for n in [
                "twinguard",
                "numpy",
                "scipy",
                "open3d",
                "fastapi",
                "sqlalchemy",
                "alembic",
                "psycopg",
                "paho-mqtt",
                "asyncua",
                "playwright",
            ]
        },
        "python": platform.python_version(),
        "images": r.get("images"),
        "frozen_file_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                ROOT / "requirements-edge.lock",
                ROOT / "requirements-analytics.lock",
                ROOT / "frontend/package-lock.json",
                *sorted((ROOT / "configs/fusion/calibration").glob("*")),
            ]
            if p.is_file()
        },
        "measurement_notes": [
            "Software-loopback on one workstation; not hardware/field latency.",
            "Commit confirmation is an observed post-transaction upper bound.",
            "Browser first-red visibility is one observed activation, not a latency quantile.",
            "OPC UA polls snapshots; not every simulator write is promised.",
            "Independent normal/critical sources: three each; targeted outage tests: one per service.",
        ],
    }
    d = ROOT / "docs/phase5"
    f = ROOT / "docs/figures/phase5"
    f.mkdir(parents=True, exist_ok=True)
    save(d / "results.json", summaries)
    save(d / "timeline.json", timeline)
    save(d / "resource_samples.json", resource)
    plt.rcParams.update(
        {"font.size": 10, "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 150}
    )

    def finish(name, title):
        plt.suptitle(title)
        plt.tight_layout()
        plt.savefig(f / name, bbox_inches="tight")
        plt.close()

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.axis("off")
    boxes = [
        ("Public sensors /\nscenario controller", 0),
        ("Mosquitto +\nread-only OPC UA", 0.19),
        ("Validated inbox /\nPostgreSQL + CAS", 0.39),
        ("Fast + Open3D\nanalytics / F1", 0.59),
        ("FastAPI / SSE /\nReact + Three.js", 0.8),
    ]
    for label, x in boxes:
        ax.text(
            x + 0.08,
            0.5,
            label,
            ha="center",
            va="center",
            transform=ax.transAxes,
            bbox={"boxstyle": "round,pad=.8", "facecolor": "#e5f0f7", "edgecolor": "#447788"},
        )
    for x in [0.16, 0.36, 0.56, 0.76]:
        ax.annotate(
            "",
            xy=(x + 0.04, 0.5),
            xytext=(x, 0.5),
            xycoords="axes fraction",
            arrowprops={"arrowstyle": "->"},
        )
    finish(
        "E4-1_architecture.png",
        "Actual implemented local services (conceptual architecture, not benchmark data)",
    )
    fig, ax = plt.subplots(figsize=(10, 4))
    sample = first or (timeline[0] if timeline else None)
    if sample:
        base = stamp(sample["receipt"])
        points = [
            ("Edge receipt", 0),
            ("Job starts", stamp(sample["job_start"]) - base),
            ("Analytics completed", stamp(sample["analytics_complete"]) - base),
            (
                "Advisory committed",
                stamp(sample.get("advisory_commit_confirmed_at", sample["advisory_available"]))
                - base,
            ),
        ]
        if browser_first and first:
            points.append(("Browser red visible", stamp(browser_first) - base))
        ax.scatter([x[1] for x in points], range(len(points)), s=60)
        ax.set_yticks(range(len(points)), [x[0] for x in points])
        ax.set_xlabel("Actual seconds after edge receipt")
    finish(
        "E4-2_message_timeline.png",
        "Observed critical software path; original scientific acquisition is retained separately",
    )
    fig, ax = plt.subplots(figsize=(11, 4))
    names = [p["run"] for p in publishers]
    x = np.arange(len(names))
    ax.bar(x, [p["distinct_observations"] for p in publishers], label="Distinct published")
    ax.bar(x, [p["missing"] for p in publishers], label="Missing")
    ax.set_xticks(x, names, rotation=60, ha="right")
    ax.legend()
    ax.set_ylabel("Observation identities")
    finish(
        "E4-3_completeness.png",
        "Published-to-durable completeness; deliberate duplicate deliveries excluded",
    )
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, key, title in zip(
        axes,
        ["iot_receipt_to_advisory_commit", "inspection_receipt_to_advisory_commit"],
        ["Fast IoT path", "Inspection path"],
    ):
        values = latencies[key]
        ax.hist(values, bins=min(35, max(1, len(values))), color="#398798")
        ax.set_title(f"{title}, n={len(values)}")
        ax.set_xlabel("Seconds: receipt to observed advisory commit")
        ax.set_ylabel("Jobs")
    finish(
        "E4-4_processing_latency.png",
        "Actual local latency distributions; inspection sample count is limited",
    )
    recovery = [p for p in r["profiles"] if "recovery_s" in p]
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar(
        [p["service"] for p in recovery], [p["recovery_s"] or 0 for p in recovery], color="#ac784b"
    )
    ax.set_ylabel("Seconds: stop request to worker/API readiness")
    finish(
        "E4-5_recovery.png",
        "Controlled local service interruption/recovery; one targeted test per service",
    )
    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
    t0 = stamp(r["started_at"])
    times = [stamp(s["at"]) - t0 for s in resource]
    axes[0].plot(times, [s.get("queue", {}).get("pending", 0) for s in resource])
    axes[0].set_ylabel("Pending jobs")
    axes[1].plot(times, [s.get("db_bytes", 0) / 1024**2 for s in resource])
    axes[1].set_ylabel("Database MiB")
    cpu = []
    for sample in resource:
        cpu.append(
            sum(float(c.get("CPUPerc", "0%").rstrip("%")) for c in sample.get("containers", []))
        )
    axes[2].plot(times, cpu)
    axes[2].set_ylabel("Summed container CPU %")
    axes[2].set_xlabel("Elapsed wall seconds (100% = one CPU core)")
    finish(
        "E4-6_resources.png", "Measured workload/queue, database storage and sampled container CPU"
    )
    for name in [
        "E4-7_dashboard.png",
        "E4-8_critical_trace.png",
        "E4_inspections.png",
        "E4_measurements.png",
        "E4_monitoring.png",
    ]:
        source = directory / "browser" / name
        if source.exists():
            shutil.copy2(source, f / name)
    if (directory / "first_red_browser.png").exists():
        shutil.copy2(directory / "first_red_browser.png", f / "E4_first_red_browser.png")
    save(
        f / "figure_source_data.json",
        {
            "run": str(directory),
            "latency_s": latencies,
            "publishers": publishers,
            "resource": resource,
            "critical": summaries["first_critical"],
        },
    )
    print(
        "Audited",
        len(obs),
        "observations;",
        len(jobs),
        "jobs;",
        len(records),
        "operational records",
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", type=Path, required=True)
    args = p.parse_args()
    run(args.run_dir)
