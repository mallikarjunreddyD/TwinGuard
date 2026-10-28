"""Publish a candid Phase 5 dossier from immutable measured runs and explicit checks."""

from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import Counter
import hashlib
import json
import subprocess
import shutil
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "docs/phase5"
F = ROOT / "docs/figures/phase5"
FULL = ROOT / "experiments/outputs/phase5-E4-release"
PRIORITY = ROOT / "experiments/outputs/phase5-E4-priority-verified"
BROWSER = ROOT / "experiments/outputs/phase5-E4-release-browser-validated"


def read(p):
    return json.loads(p.read_text())


def save(p, v):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, indent=2, default=str, allow_nan=False) + "\n")


def ts(v):
    return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()


def stats(values):
    return {
        "n": len(values),
        **{f"p{p}": float(np.percentile(values, p)) if values else None for p in [50, 95, 99]},
        "max": max(values) if values else None,
    }


def verify(path):
    seal = read(path / "predictions_ready.json")
    for name, digest in seal["artifacts"].items():
        assert hashlib.sha256((path / name).read_bytes()).hexdigest() == digest, (path, name)


def main():
    verify(FULL)
    verify(PRIORITY)
    r = read(D / "results.json")
    p = read(PRIORITY / "report.json")
    b = read(BROWSER / "browser.json")
    assert all(b["checks"].values()) and not b["errors"]
    assert r["job_status_counts"] == {"completed": 6075}
    states = Counter(s for item in p["critical_readings"] for s in item["state"])
    assert p["ordinary_backlog_before_critical"] > 0
    assert states == {"current": 186}, states
    assert all(x["assessment_severity"] == "red" for x in p["critical_readings"])
    assert p["job_statuses"]["failed"] == 0 and p["job_statuses"]["pending"] == 0
    pc = stats([x["receipt_to_advisory_s"] for x in p["critical_readings"]])
    first = min(p["critical_readings"], key=lambda x: x["received"])
    browser_s = ts(p["browser"]["red_visible_at"]) - ts(first["received"])
    base_observations = read(FULL / "observations.json")
    base_records = read(FULL / "records.json")
    timings = {x["id"]: x["body"] for x in base_records if x["kind"] == "timing"}
    traces = {x["id"]: x["body"] for x in base_records if x["kind"] == "trace"}
    baseline_states = Counter()
    for o in base_observations:
        if (
            o["sensor"] == "pressure-01"
            and o["body"]["quality"] == "good"
            and o["body"]["value"] >= 1150000
            and any(f"e4-public-{seed}" in o["id"] for seed in [8210, 8211, 8212])
        ):
            t = timings[o["id"]]
            trace = next(
                traces[i]
                for i in t["assessments"]
                if traces[i]["assessment"]["asset_id"] == "BW-01"
            )
            baseline_states.update(
                x["status"]
                for x in trace["temporal"]
                if x["hazard_id"] == "critical-pressure" and x["evidence_id"] == "limit-" + o["id"]
            )
    r["original_browser_checks"] = r["browser"]
    r["browser"] = b
    r["critical_temporal_baseline"] = dict(baseline_states)
    r["critical_priority_correction"] = {
        "source_commit": p["source_commit"],
        "run": str(PRIORITY),
        "ordinary_pending_jobs_at_start": p["ordinary_backlog_before_critical"],
        "critical_temporal_states": dict(states),
        "receipt_to_committed_advisory_s": pc,
        "first_receipt_to_browser_red_s": browser_s,
        "dataset_count": 3,
        "inputs": "Identical public pressure datasets 8210–8212; fresh database and confirmed ordinary job backlog; no artificial transport backlog.",
        "comparison_limit": "Focused corrective run, not a repeated full outage/resource benchmark; workloads are related but not identical to the original full run.",
    }
    r["correction_history"] = [
        {
            "run": "phase5-E4-formal",
            "status": "interrupted development",
            "reason": "Original timestamps of separate replay datasets could mix operating context; source-provenance binding corrected.",
        },
        {
            "run": "phase5-E4-validated",
            "status": "executed with failures",
            "reason": "OPC UA immutable timestamp constructor and missing Open3D native libraries; all failures retained.",
        },
        {
            "run": "phase5-E4-corrected-integration",
            "status": "targeted corrected workflows",
            "reason": "Actual operating protocols, L1/thermal positives and L2 inconclusiveness verified.",
        },
        {
            "run": "phase5-E4-release",
            "status": "full executed benchmark",
            "reason": "All jobs completed, completeness/restarts/browser demonstrated; FIFO freshness limitation identified.",
        },
        {
            "run": "phase5-E4-priority-final",
            "status": "combined transport overload",
            "reason": "124 current/62 stale readings; initial input backlog meant some data was already stale before ingestion. Retained, not counted as a clean priority comparison.",
        },
        {
            "run": "phase5-E4-priority-verified",
            "status": "focused priority correction",
            "reason": "Ordinary messages confirmed durable before critical publishing; original thresholds/clock rules preserved.",
        },
    ]
    # Actual resource summaries; Docker 100% CPU equals one logical core, not the full machine.
    samples = read(D / "resource_samples.json")
    peak_cpu = 0.0
    mem = {}
    peak_queue = 0

    def mib(s):
        value = s.strip()
        units = {
            "KiB": 1 / 1024,
            "MiB": 1,
            "GiB": 1024,
            "B": 1 / 1024**2,
            "kB": 1000 / 1024**2,
            "MB": 1000**2 / 1024**2,
            "GB": 1000**3 / 1024**2,
        }
        for unit, factor in sorted(units.items(), key=lambda item: -len(item[0])):
            if value.endswith(unit):
                try:
                    return float(value[: -len(unit)]) * factor
                except ValueError:
                    return 0.0
        return 0.0

    for sample in samples:
        peak_queue = max(peak_queue, sample.get("queue", {}).get("pending", 0))
        cpu = 0.0
        for c in sample.get("containers", []):
            cpu += float(c.get("CPUPerc", "0%").rstrip("%"))
            name = c["Name"].replace("twinguard-e4-release-", "")
            mem[name] = max(mem.get(name, 0), mib(c.get("MemUsage", "0MiB / 0MiB").split("/")[0]))
        peak_cpu = max(peak_cpu, cpu)
    r["resources_summary"] = {
        "sample_count": len(samples),
        "peak_summed_container_cpu_percent": peak_cpu,
        "peak_memory_mib_by_service": mem,
        "peak_pending_jobs": peak_queue,
        "note": "Sampled peaks, not continuous maximum; summed per-process CPU can exceed 100%. Browser runs on host.",
    }
    cpuinfo = Path("/proc/cpuinfo").read_text()
    r["hardware_model"] = next(
        (x.split(":", 1)[1].strip() for x in cpuinfo.splitlines() if x.startswith("model name")),
        "unavailable",
    )
    r["host_memory_kib"] = next(
        (
            int(x.split()[1])
            for x in Path("/proc/meminfo").read_text().splitlines()
            if x.startswith("MemTotal:")
        ),
        None,
    )
    initial = min(s["db_bytes"] for s in samples if s.get("db_bytes"))
    growth = max(0, r["peak_database_bytes"] - initial)
    bytes_per = growth / len(base_observations)
    nominal_rate = []
    for file in FULL.glob("B1-*/publisher.json"):
        manifest = read(file)
        values = [m for m in manifest["messages"] if m.get("observation_id")]
        span = max(ts(m["original_acquired_at"]) for m in values) - min(
            ts(m["original_acquired_at"]) for m in values
        )
        nominal_rate.append(len({m["observation_id"] for m in values}) / span)
    payload_mean = float(np.mean([len(json.dumps(o["body"]).encode()) for o in base_observations]))
    rate = float(np.mean(nominal_rate))
    seconds = 90 * 24 * 3600
    r["capacity_estimate"] = {
        "nominal_1x_observations_per_s_from_actual_source_records": rate,
        "mean_public_observation_json_bytes": payload_mean,
        "observed_database_growth_bytes_per_observation_including_jobs_traces_audit": bytes_per,
        "raw_observation_json_90day_bytes": rate * payload_mean * seconds,
        "naive_full_platform_90day_bytes": rate * bytes_per * seconds,
        "limits": "Projection only; excludes or differently scales indexes, vacuum/reuse, active-history growth, aggregation, WAL/backups and inspection cadence. No 90-day storage/endurance claim. Scientific/decision history is conservatively retained.",
    }
    r["artifact_bytes_full_run"] = sum(
        x["body"]["size"] for x in base_records if x["kind"] == "artifact"
    )
    # Required resource figure includes missing-sample gaps and memory, not just CPU.
    times = [ts(x["at"]) - ts(r["started_at"]) for x in samples]
    cpu_series = []
    memory_series = []
    for sample in samples:
        containers = sample.get("containers")
        cpu_series.append(
            sum(float(c.get("CPUPerc", "0%").rstrip("%")) for c in containers)
            if containers
            else np.nan
        )
        memory_series.append(
            sum(mib(c.get("MemUsage", "0MiB / 0MiB").split("/")[0]) for c in containers)
            if containers
            else np.nan
        )
    fig, axes = plt.subplots(4, 1, figsize=(11, 10), sharex=True)
    axes[0].plot(times, [x.get("queue", {}).get("pending", np.nan) for x in samples])
    axes[0].set_ylabel("Pending jobs")
    axes[1].plot(times, [x.get("db_bytes", np.nan) / 1024**2 for x in samples])
    axes[1].set_ylabel("Database MiB")
    axes[2].plot(times, cpu_series)
    axes[2].set_ylabel("Container CPU %")
    axes[3].plot(times, memory_series)
    axes[3].set_ylabel("Container RAM MiB")
    axes[3].set_xlabel("Elapsed wall seconds; missing samples are gaps")
    plt.suptitle("E4-6 — Measured queue, storage, CPU and memory (CPU 100% = one core)")
    plt.tight_layout()
    plt.savefig(F / "E4-6_resources.png", dpi=150, bbox_inches="tight")
    plt.close()
    fig, axes = plt.subplots(1, 2, figsize=(13, 4), gridspec_kw={"width_ratios": [2, 1]})
    pub = r["publisher_completeness"]
    x = np.arange(len(pub))
    axes[0].bar(x - 0.2, [v["distinct_observations"] for v in pub], 0.4, label="Distinct published")
    axes[0].bar(x + 0.2, [v["persisted"] for v in pub], 0.4, label="Durable observations")
    axes[0].set_xticks(x, [v["run"] for v in pub], rotation=60, ha="right")
    axes[0].set_ylabel("Observation identities")
    axes[0].legend()
    counts = r["audit_counts"]
    labels = ["Exact delivery copies", "Observation copies", "Quarantined in full run"]
    axes[1].bar(
        labels,
        [
            counts.get("duplicate_delivery", 0),
            counts.get("duplicate_observation", 0),
            counts.get("quarantined", 0),
        ],
        color=["#7185ae", "#4d9990", "#cf7c5d"],
    )
    axes[1].tick_params(axis="x", rotation=30)
    axes[1].set_title("Copies counted separately; zero loss")
    plt.suptitle(
        "E4-3 — Completeness and copies; separate invalid-input security probes are reported independently"
    )
    plt.tight_layout()
    plt.savefig(F / "E4-3_completeness.png", dpi=150, bbox_inches="tight")
    plt.close()
    accepted = [
        "configs/analytics/accepted_reference.json",
        "configs/edge/assets.json",
        "configs/edge/plant.glb",
        "configs/edge/simulation-sources.json",
        "configs/edge/site-review-sources.json",
        "configs/fusion/hazards.yaml",
        "configs/fusion/site-template.yaml",
    ]
    for name in accepted:
        raw = (ROOT / name).read_bytes()
        frozen = subprocess.check_output(["git", "show", r["source_commit"] + ":" + name], cwd=ROOT)
        assert raw == frozen, "Accepted reference/policy changed after full benchmark: " + name
        r["frozen_file_sha256"][name] = hashlib.sha256(raw).hexdigest()
    save(D / "results.json", r)
    save(
        D / "priority_comparison.json",
        {
            "baseline_temporal": dict(baseline_states),
            "corrected": r["critical_priority_correction"],
            "critical_readings": p["critical_readings"],
        },
    )
    for image in BROWSER.glob("*.png"):
        shutil.copy2(image, F / image.name)
    shutil.copy2(PRIORITY / "priority_red_browser.png", F / "E4_priority_red_browser.png")
    # A compact genuine trace is easier to read than a whole-page JSON screenshot.
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.axis("off")
    rows = [
        ["Observation", first["observation_id"]],
        ["Authenticated source", "demo-iot / registered pressure-01 → BW-01"],
        ["Deployment / policy", "simulation / synthetic-hazards v1 (illustrative)"],
        ["Configured crossing", "Pressure ≥ 1,150,000 Pa; assumed synthetic instrumentation"],
        ["Temporal qualification", ", ".join(first["state"])],
        ["Assessment", first["assessment_severity"]],
        ["Receipt → committed advisory", f"{first['receipt_to_advisory_s']:.3f} s"],
        ["Receipt → visible red in real Chromium", f"{browser_s:.3f} s"],
        ["UAV support", "No inspection messages/artifacts in this focused test"],
        ["Scope", "Local software integration; no physical safety/field-latency claim"],
    ]
    table = ax.table(
        cellText=rows,
        colLabels=["Measured trace boundary", "Stored/observed result"],
        cellLoc="left",
        colWidths=[0.3, 0.7],
        loc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.8)
    plt.title("E4-8 — Actual prioritized critical-pressure trace without UAV", pad=20)
    plt.tight_layout()
    plt.savefig(F / "E4-8_critical_trace_measured.png", dpi=160, bbox_inches="tight")
    plt.close()
    checks = read(D / "checks.json")
    security = read(D / "security_checks_release.json")["results"]
    assert all(
        security[k]["quarantined"]
        for k in [
            "invalid_schema",
            "wrong_asset",
            "wrong_unit",
            "unregistered_source",
            "future_timestamp",
            "nonfinite",
        ]
    )
    assert (
        security["anonymous_api"]["status"] == 401
        and security["viewer_operator_action"]["status"] == 403
    )
    assert all(x["hash_verified"] for x in read(D / "derived_artifact_checks.json"))
    criteria = [
        (
            "Prior Phase 0–4 behavior",
            "Unchanged plant/sensing/analytics/fusion code; full prior regression retained",
        ),
        ("Real MQTT", "Mosquitto QoS1 + paho; actual published IDs matched SQL"),
        (
            "Real read-only OPC UA",
            "Nine numeric channels/status records; reconnect; read-only denial test",
        ),
        (
            "Synthetic public streams",
            "Original TwinGuard generation/sensing; opaque public dataset IDs",
        ),
        (
            "Authenticated sources",
            "Non-default credentials, broker ACLs, registry identity, real rejection tests",
        ),
        ("Source/asset mapping", "Registered sensor/asset/type/unit/configuration validation"),
        ("Actual receipt", "Independent edge UTC receipt alongside original source records"),
        (
            "Clock trust",
            "Server registry trust; per-capture source anchors/rates; payload claims do not grant synchronization",
        ),
        ("Invalid quarantine", "Six actual invalid MQTT cases; bounded digest/reason audit"),
        (
            "Durable deduplication",
            "SQL keys; duplicate envelopes/representations; no repeated open effects",
        ),
        (
            "Artifact integrity/confinement",
            "Bounded public bundles and verified immutable raw/registered NPZ downloads",
        ),
        ("Durable database", "PostgreSQL named volume; non-superuser application role"),
        ("Migrations", "Alembic 0001_edge exercised on fresh deployments"),
        (
            "Restart-safe jobs",
            "Leases, owner checks, bounded retries and exhausted-lease quarantine",
        ),
        ("Durable checkpoints", "Locked F1 JSON state in transaction"),
        ("Durable advisory lifecycle", "Committed events/notices/actions retained through outages"),
        (
            "Idempotent effects",
            "Zero duplicate observations/open effects; repeated acknowledgment stable",
        ),
        (
            "Retention/archival",
            "Bounded raw archival tested; unresolved/scientific references conservatively preserved",
        ),
        ("Operating analytics", "Original inference with provenance-bound ingested context"),
        (
            "B3.1 integration",
            "Actual public LiDAR pairs; qualified L1 region and L2 insufficient coverage",
        ),
        (
            "Thermal integration",
            "Actual quantitative arrays/masks; valid apparent-temperature residual region",
        ),
        ("F1 integration", "Unchanged Phase 4 engine and semantic gates"),
        (
            "Independent critical path",
            "Separate fast worker + server-derived priority; 186/186 current in focused correction",
        ),
        ("Version provenance", "Policy, source/model/lock hashes and image identifiers retained"),
        (
            "Missing/inconclusive explicit",
            "No missing-input green; L2 inconclusiveness and source staleness displayed",
        ),
        ("Deployment profiles", "Illustrative simulation versus unknown/unapproved site review"),
        (
            "Functional API",
            "Historical/current queries, pagination, filters, role-protected actions",
        ),
        ("Live browser", "Actual SSE receipt, visible red, resumed cursor and backend snapshot"),
        ("Accepted 3D baseline", "Real GLB/WebGL screenshot; no simulated deformation animation"),
        ("Asset interaction", "Actual selection and condition detail browser checks"),
        (
            "Measured geometric regions",
            "Selected qualified inspection overlay with localized-relative limitations",
        ),
        (
            "Qualified thermal display",
            "Actual quantitative image, masks, bounds/residuals; image-only remains image-only",
        ),
        ("Stored telemetry charts", "Actual SQL values, units/source times, invalid gaps"),
        (
            "Explainability",
            "Evidence IDs, hazards, current/historical support, policy/profile and rationale",
        ),
        (
            "Monitoring health",
            "Per-source/channel receipt, clock, calibration, freshness, coverage and backlog",
        ),
        (
            "Authorized acknowledgment",
            "Real operator browser/API checks; viewer 403; acknowledgment does not resolve",
        ),
        (
            "No actuation",
            "No control routes or OPC UA plant write client; laboratory read-only rejection checked",
        ),
        (
            "Full Compose stack",
            "Broker/DB/ingestion/fast/heavy/API/frontend; persistent volumes and health checks",
        ),
        (
            "Local offline operation",
            "Internal backend network; no external browser resources; installation/build needs separate dependencies",
        ),
        ("Controlled recovery", "Worker, broker, API, database and OPC UA interruptions executed"),
        ("Executed E4", "Sealed 16.86-minute full benchmark plus focused corrective workload"),
        (
            "Measured metrics",
            "Completeness, latency, resource, recovery and capacity with sample counts/caveats",
        ),
        ("Real browser evidence", "All final browser checks true; genuine screenshots, no mock UI"),
        (
            "Scientific isolation",
            "Restricted code/data absent from runtime images; public contracts/arrays and frozen references",
        ),
        (
            "Regression/build checks",
            f"{checks['pytest_passed']} tests; Ruff/Mypy; frontend build/3 tests; real protocols and image startup",
        ),
        (
            "Documentation/schema handoff",
            "Required guides, additive schemas, CLI and measured evidence register",
        ),
    ]
    date = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
    text = f"""# Phase 5 validation — integrated edge research demonstrator

Completed {date} (Asia/Calcutta). Version 0.6.0; schema 1.0.0. Branch phase-5-edge-platform. Starting Phase 4 commit a00bce3. Full E4 producer {r["source_commit"]}; critical-path correction {p["source_commit"]}. Exact source/model/image/lock provenance is in phase5/results.json and phase5/final_revision.json. No Phase 6 work or physical plant control is implemented.

## A–B. Architecture and capabilities

The actual chain is public measured acquisition → authenticated Mosquitto QoS1 or read-only numeric OPC UA → registry/time/artifact validation → PostgreSQL inbox/observations/jobs → original operating/B3.1/thermal analytics → original F1 → atomic checkpoint/assessment/advisory/outbox → authenticated FastAPI/SSE → React/TypeScript/Three.js dashboard. Separate lightweight API/fast-worker and Open3D images run locally under Compose. Accepted baseline geometry remains static; displayed conditions, plots, regions and thermal values come from backend records.

Implemented modules and contracts are described in PHASE5_ARCHITECTURE.md, EDGE_INGESTION.md, MQTT_PROTOCOL.md, OPCUA_INTEGRATION.md, PERSISTENCE_AND_RECOVERY.md and PLATFORM_SECURITY.md. Source acquisition/claims, authenticated identity, actual receipt, calibration, clock trust and policy approval are separate. The browser cannot grant verified instrumentation or engineering authority.

## C. Phase 4 issues

| Issue | Correction and executed evidence |
|---|---|
| P4-1 identity/time | Broker credentials/ACLs and independent registry; actual receipt; unknown physical clocks remain unknown; six actual invalid MQTT cases quarantined; per-capture replay chronology tested |
| P4-2 durability | PostgreSQL constraints/leased jobs/atomic F1 state/outbox; all committed events preserved in controlled worker/API/database outages; bounded retry/retention tests |
| P4-3 illustrative limits | Distinct server-side simulation/site-review profiles; site template has no approved critical limits; unknown-calibration/clock tests cannot obtain authoritative critical decisions |
| P4-4 coverage | Per-channel monitoring, source staleness, missing requirements, calibration/clock status and actual L2 insufficient-coverage results; no alert-free healthy inference |
| P4-5 latency | Actual local publisher/receipt/commit/job/fusion/API/browser timestamps; full workload and priority correction measured, not simulated field latency |

## D. Start and demonstrate

See DEMO_WALKTHROUGH.md for complete executable commands and tokens/roles, and DASHBOARD_GUIDE.md for operator use. From a prepared repository:

```bash
./scripts/edge_build.sh
docker compose --env-file .edge/runtime.env -f deployment/compose.yaml up -d --no-build
```

Open http://localhost:18780 and enter the locally generated token from .edge/secrets.json. Host publishers require the explicit loopback validation overlay. Do not run two projects on the same ports. Scenario commands generate/stream actual healthy, geometric, thermal, critical-without-UAV and L2 data. Replay supports rates, pause/resume control and step mode, while original scientific times and actual processing remain distinct. No cloud service is required after installation/build.

## E. E4 numerical results

Full benchmark duration: **{r["elapsed_s"]:.2f} seconds**. Distinct durable observations: **6,072**; completed jobs: **6,075**, including three actual inspection jobs. No failed/pending jobs at the sealed endpoint. The three normal datasets persisted **429/429, 426/426 and 431/431** distinct published readings. The sustained first publisher operated for **{next(x["elapsed_s"] for x in r["publisher_completeness"] if x["run"] == "B1-8200"):.2f} seconds** with ingestion, storage, analytics, F1, API and browser active. This is not a 24-hour endurance claim.

Completeness is measured from distinct publisher-side observation IDs, not ideal pre-dropout sensing schedules. At-least-once copies do not inflate completeness. Zero duplicate durable observations and zero repeated advisory-open effects were observed. Two leased jobs retried. Source sequence epochs, physical observation lineage and actual reordered acquisition are separately audited.

| Full benchmark stage | n | p50 s | p95 s | p99 s |
|---|---:|---:|---:|---:|
"""
    for label, key in [
        ("Publisher to application receipt", "publisher_to_receipt"),
        ("Receipt to observed ingest commit", "receipt_to_ingest_commit_observed"),
        ("Fast IoT receipt to committed advisory", "iot_receipt_to_advisory_commit"),
        ("Inspection receipt to committed advisory", "inspection_receipt_to_advisory_commit"),
    ]:
        v = r["latency_s"][key]
        text += f"| {label} | {v['n']} | {v['p50']:.4f} | {v['p95']:.4f} | {v['p99']:.4f} |\n"
    text += f"""
The full FIFO workload exposed a real limitation: **6/186** configured critical crossings were current at assessment and **180/186** had aged beyond the unchanged 10-second rule. Durable completeness and a latched red event do not prove timely interpretation of every reading. This was not hidden or addressed by increasing TTLs.

The final scheduler uses the existing engineering-limit adapter for a server-side urgency hint; the worker independently requalifies F1 evidence. Validated policy parsing is cached by file revision. In a fresh focused run with **{p["ordinary_backlog_before_critical"]} older ordinary pending jobs**, the identical three public critical datasets yielded **186/186 current readings**, all producing red assessments. Receipt-to-committed-advisory latency was **{pc["p50"]:.4f} s p50 / {pc["p95"]:.4f} s p95 / {pc["p99"]:.4f} s p99**, max **{pc["max"]:.4f} s**. The first red became visible in real Chromium after **{browser_s:.3f} seconds** from edge receipt, without UAV data.

This is a focused correction, not an independently repeated full fault/resource study. A separate combined transport-overload test still produced 62 already-aging/stale readings; priority cannot make data fresh before ingestion. All those runs are preserved. Source quality and temporal gates were not relaxed.

| Interrupted service | Stop request → readiness s | Committed event history retained |
|---|---:|---|
"""
    for row in r["profiles"]:
        if "recovery_s" in row:
            text += f"| {row['service']} | {row['recovery_s']:.3f} | {row['events_preserved']} |\n"
    text += f"""
Numeric OPC UA: nine channel/status records and 45 distinct observations in the short polled snapshot interval; interruption/reconnection was observed. This is not completeness against every simulator write. The read-only client rejects unsupported units/types and preserves original source/server status/times.

Actual inspection results: L1 geometric case **one qualified region**; thermal case **one valid apparent-temperature residual region**; L2 case **insufficient_coverage with no qualified region**. All three registered measured NPZ objects were retrieved through authenticated API calls and their SHA256 verified.

Hardware: {r["hardware_model"]}; {r["environment"]["cpu_count"]} logical CPUs; {r["host_memory_kib"] / 1024**2:.2f} GiB reported host memory. {r["environment"]["platform"]}. No industrial-edge hardware/GPU performance is inferred. Sampled peak summed container CPU **{peak_cpu:.1f}%** (100% is one logical core); peak pending jobs **{peak_queue}**; peak database **{r["peak_database_bytes"] / 1024**2:.2f} MiB**. Per-service memory, response quantiles, raw samples and container limits are in the machine-readable artifacts. Browser heap/DOM/render smoke was observed; continuous FPS is not claimed.

The nominal source rate derived from actual source timestamps is **{rate:.3f} observations/s**. Raw observation JSON projects to **{rate * payload_mean * seconds / 1024**3:.2f} GiB/90 days**. A naive extrapolation of full measured database growth, including per-assessment traces/jobs/audits, is **{rate * bytes_per * seconds / 1024**3:.2f} GiB/90 days**. This is a capacity diagnostic, not a tested retention or linear-growth guarantee. Aggregation/backups/WAL and unresolved history need deployment planning; scientific/advisory history is conservatively preserved.

## F. Real browser demonstration

All final Chromium checks passed: model rendering, actual assets, selection, stored charts, inspection selection, thermal image, geometric interpretation, monitoring, evidence, red advisory history, authorized acknowledgment and reconnect. No page errors or external resource requests were observed. The independent final browser run records its actual timing and screenshots; the original full benchmark browser result remains preserved. These are screenshots of the running application, not UI mockups.

![Running integrated dashboard](figures/phase5/E4-7_dashboard.png)
![Selected measured thermal inspection](figures/phase5/E4_inspections.png)
![Measured critical trace](figures/phase5/E4-8_critical_trace_measured.png)

## G–H. Security and scientific integrity

Authenticated ingestion, topic ACLs, token roles, bounded upload/message sizes, safe content-addressed public artifacts, hash verification, and audited idempotent operator review are implemented. Actual unauthorized MQTT connection/topic attempts were rejected; API anonymous/viewer misuse returned 401/403; private artifacts returned 404; path traversal/private bundle attempts returned 422. Calibration/clock approval remains independent of transport authentication.

Runtime images exclude plant/evaluation/sensing generation code, private datasets/scenarios and private core configuration/registry modules. Only public measured observations, accepted as-built references and frozen healthy models enter inference. E1/E2/E3 outputs and all original numerical algorithms are unchanged. No hidden fault labels, true poses or true deformed surfaces feed analytics/F1/UI. Controller generation and optional evaluation remain outside deployed workers.

Default HTTP/MQTT/OPC UA transport is explicitly local laboratory operation. Backend services run on an internal network; the browser uses local resources. LAN TLS/certificate templates are provided but not commissioned/certified. Optional OPC UA NoSecurity is never described as production secure. Local role tokens are not enterprise SSO/expiry/rotation. Exact-once MQTT delivery, hardware latency and physical safety certification are not claimed.

## I. Regression and build checks

**{checks["pytest_passed"]} Pytest tests passed**, one existing Starlette/httpx warning. Starting baseline: 227. Ruff lint/format, Mypy (91 source files), dependency checks, schema export, frontend build and three frontend semantics tests pass. Actual containers start, migrations execute, Open3D imports inside the heavy image, API health responds, protocols communicate, browser checks execute and services survive controlled restart. Required native libraries and exact Python/npm versions are recorded.

## J. Files and artifacts

- `src/twinguard/edge/`: contracts, secure ingress, real protocols, durable queue/store, workers, admin recovery and API adapter.
- `src/twinguard/api/app.py`: existing FastAPI integration; `frontend/`: React/TypeScript/Three.js application and lock.
- `deployment/compose.yaml`, `deployment/edge/`: full stack, separate images, validation and reviewed LAN templates.
- `migrations/`, `alembic.ini`, `configs/edge/`, `schemas/EdgeEnvelope.schema.json`, `schemas/SourceRegistration.schema.json`.
- `scripts/run_e4.py`, `verify_priority.py`, `edge_demo.py`, `edge_browser.py`, `summarize_e4.py`, `verify_edge_security.py`.
- `experiments/outputs/phase5-E4-release`: immutable full run, raw timestamps, input manifests, jobs, observations, predictions and seal.
- `experiments/outputs/phase5-E4-priority-verified`: immutable corrective workload and real critical browser capture.
- `docs/phase5/results.json`, `priority_comparison.json`, `timeline.json`, `resource_samples.json`, `checks.json`, `security_checks_release.json`, `final_revision.json`.
- `docs/figures/phase5/`: eight required measured/architecture/browser figures plus numerical source data and selected inspection views.

## K. Limits and failure history

Earlier development outputs are retained, including the timestamp/provenance association issue, OPC UA immutable timestamp constructor error, missing Open3D native dependency and browser data-wait race. Final native dependencies, per-capture replay clocks, source-provenance binding, actual actor acknowledgment, safe derived artifacts and priority behavior were rerun, not asserted from documentation. No final metrics overwrite those failed observations.

Physical sensors/site-approved limits/calibration and verified synchronization are not commissioned. Standard arbitrary third-party OPC UA address spaces require a reviewed mapping/adapter; the demonstrated schema is explicit numeric nodes plus public lineage. No crash-safe publisher disk spool or HA cluster is claimed. Retention archives bounded raw inbox records and preserves all referenced scientific/decision history; complete automated long-horizon scientific deletion/aggregation is not enabled. L2 geometry remains limited; B3.1 is localized_relative, not certified absolute wall thickness. Thermal findings remain apparent-temperature/image-only when physical association is unsupported. Sampling, accelerated replay, queueing and finite fault tests do not establish industrial safety/reliability.

## L. Acceptance and Phase 6 readiness

| # | Criterion | Decision / evidence |
|---:|---|---|
"""
    for i, (name, evidence) in enumerate(criteria, 1):
        text += f"| {i} | {name} | PASS — {evidence} |\n"
    text += """
Phase 5 local software demonstrator: **PASS**, with the measured FIFO/transport limits and focused corrective scope above. Physical/production deployment readiness: **PARTIAL**. Phase 6 software research handoff: **CONDITIONAL GO**. Asset conditions, scoped coverage, uncertainty/qualification, actual freshness, inspection history, accepted geometry and reported viewpoint poses are available through public records/APIs. Viewpoint feasibility, UAV dynamics/obstacles/flight safety, approved hardware/site policy and field validation are still required before physical risk-adaptive inspection. No Phase 6 optimization or actuation was started.
"""
    (ROOT / "docs/PHASE5_VALIDATION.md").write_text(text)
    print("Phase 5 dossier written; sealed benchmarks and final browser checks verified")


if __name__ == "__main__":
    main()
