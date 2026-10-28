"""Read-only E3 reporting: sealed predictions, measured charts and audit tables."""

from pathlib import Path
from typing import Any
from collections import Counter
from datetime import datetime
import json
import csv
import shutil
import numpy as np
from .analytics import verify_seal
from twinguard.fusion.io import save


def report_figures(root: Path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    report = json.loads((root / "report.json").read_text())
    output = root / "figures"
    output.mkdir(exist_ok=True)

    def png(fig, name):
        fig.tight_layout()
        fig.savefig(output / name, dpi=170, bbox_inches="tight")
        plt.close(fig)

    def case(track, condition, method="F1"):
        row = next(
            r
            for r in report[track]["rows"]
            if r["condition"] == condition and r["method"] == method
        )
        path = root / ("controlled" if track == "controlled" else "end_to_end") / row["case_id"]
        verify_seal(path / method)
        return path, row

    data: dict[str, Any] = {}
    path, row = case("controlled", "E3-C06")
    evidence = json.loads((path / "inputs/evidence.json").read_text())
    base = min(datetime.fromisoformat(e["acquired_at"].replace("Z", "+00:00")) for e in evidence)
    fig, ax = plt.subplots(figsize=(11, 4.5))
    times = []
    ttl = {
        "critical_pressure_limit": 10,
        "critical_temperature_limit": 10,
        "abnormal_process_pressure_residual": 10,
        "localized_geometric_change": 3600,
        "abnormal_thermal_residual": 300,
    }
    for i, e in enumerate(evidence):
        acquired = (
            datetime.fromisoformat(e["acquired_at"].replace("Z", "+00:00")) - base
        ).total_seconds()
        available = (
            datetime.fromisoformat(e["available_at"].replace("Z", "+00:00")) - base
        ).total_seconds()
        window = ttl[e["hypothesis"]]
        ax.plot([acquired, min(acquired + window, 20)], [i, i], lw=5, alpha=0.25)
        ax.scatter(acquired, i, marker="o", c="black")
        ax.scatter(available, i, marker=">", c="red")
        times.append(
            {
                "id": e["evidence_id"],
                "acquired_s": acquired,
                "available_s": available,
                "window_s": window,
            }
        )
    ax.set_yticks(range(len(evidence)), [e["hypothesis"] for e in evidence])
    ax.set(
        xlabel="Simulation seconds (circle acquisition, arrow availability)",
        title="V1 — Acquisition, availability and hazard-specific windows; LiDAR absent",
    )
    data["V1"] = times
    png(fig, "V1_evidence_timeline.png")
    history = json.loads((path / "F1/history.json").read_text())
    trace = [d for d in history if d["assessment"]["asset_id"] == "BW-01"][-1]
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.axis("off")
    table = [
        [
            "severity / confidence",
            trace["assessment"]["severity"] + " / " + trace["assessment"]["confidence_status"],
        ],
        ["policy", trace["assessment"]["policy_id"] + " " + trace["assessment"]["policy_version"]],
        ["triggered hazards", ", ".join(trace["triggered_hazards"])],
        ["current supporting IDs", "\n".join(trace["positive_ids"])],
        ["missing required coverage", ", ".join(trace["missing_requirements"])],
        ["action", trace["assessment"]["recommended_action"]],
    ]
    tab = ax.table(cellText=table, colWidths=[0.25, 0.75], cellLoc="left", loc="center")
    tab.auto_set_font_size(False)
    tab.set_fontsize(8)
    tab.scale(1, 2.8)
    ax.set_title("V2 — Actual machine decision trace: critical pressure without UAV corroboration")
    data["V2"] = trace
    png(fig, "V2_decision_trace.png")
    path, _ = case("controlled", "E3-C07")
    history = json.loads((path / "F1/history.json").read_text())
    trace = [d for d in history if d["assessment"]["asset_id"] == "BW-01"][-1]
    status = {t["evidence_id"]: t for t in trace["temporal"]}
    values: list = [(key, d["age_s"], d["status"]) for key, d in status.items()]
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.barh(
        [v[0].split("-")[-1] for v in values],
        [v[1] for v in values],
        color=["tab:red" if v[2] == "stale" else "tab:blue" for v in values],
    )
    ax.set(
        xlabel="Acquisition age at assessment (seconds)",
        title="V3 — Stale thermal excluded; current critical pressure independently raises red",
    )
    data["V3"] = values
    png(fig, "V3_stale_and_critical.png")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    x: Any = np.arange(3)
    for ax, track, title in zip(
        axes,
        ["controlled", "end_to_end"],
        ["Controlled policy semantics (E3-A)", "Actual upstream analytics (E3-B)"],
    ):
        for offset, method in [(-0.18, "F0"), (0.18, "F1")]:
            m = report[track]["metrics"][method]
            values = [
                m["event_recall"] or 0,
                m["false_advisory_rate"] or 0,
                m["unknown_fraction_mean"] or 0,
            ]
            ax.bar(x + offset, values, 0.36, label=method)
        ax.set_xticks(
            x,
            [
                "severity-qualified\nevent recall",
                "negative-scenario\nfalse advisory rate",
                "unknown\nassessment fraction",
            ],
        )
        ax.set(ylim=(0, 1.05), title=title)
        ax.legend()
    fig.suptitle("V4 — Identical evidence; separate controlled and end-to-end populations")
    png(fig, "V4_F0_F1_comparison.png")
    path, _ = case("end_to_end", "critical_pressure")
    fig, ax = plt.subplots(figsize=(11, 4.5))
    codes = {"unknown": 0, "green": 1, "amber": 2, "red": 3}
    for method in ["F0", "F1"]:
        h = [
            d
            for d in json.loads((path / method / "history.json").read_text())
            if d["assessment"]["asset_id"] == "BW-01"
        ]
        base = datetime.fromisoformat(h[0]["assessment"]["assessed_at"].replace("Z", "+00:00"))
        x = [
            (
                datetime.fromisoformat(d["assessment"]["assessed_at"].replace("Z", "+00:00")) - base
            ).total_seconds()
            for d in h
        ]
        y = [codes[d["assessment"]["severity"]] for d in h]
        ax.step(x, y, where="post", label=method)
        data["V5-" + method] = {"seconds": x, "severity_codes": y}
    ax.set_yticks(list(codes.values()), list(codes))
    ax.set(
        xlabel="Simulated assessment time seconds; 5 s cadence",
        title="V5 — Measured condition transitions and qualified recovery",
    )
    ax.legend()
    png(fig, "V5_condition_timeline.png")
    statuses = sorted(
        {
            key
            for row in report["end_to_end"]["rows"]
            for key in row.get("temporal_status_counts", {})
        }
    )
    fig, ax = plt.subplots(figsize=(12, 4.5))
    x = np.arange(len(statuses))
    for offset, method in [(-0.18, "F0"), (0.18, "F1")]:
        counter: Counter[str] = Counter()
        for row in report["end_to_end"]["rows"]:
            if row["method"] == method:
                counter.update(row.get("temporal_status_counts", {}))
                counter["missing_required_coverage"] += row.get(
                    "missing_requirement_assessments", 0
                )
        ax.bar(x + offset, [counter[s] for s in statuses], 0.36, label=method)
        data["V6-" + method] = dict(counter)
    ax.set_xticks(x, statuses, rotation=20)
    ax.set(
        ylabel="Hazard/evidence applicability decisions (repeated assessments)",
        title="V6 — Actual freshness/quality classification; F0 records diagnostics but ignores them for agreement",
    )
    ax.legend()
    png(fig, "V6_evidence_quality.png")
    conditions = [
        c for c, d in report["end_to_end"]["metrics"]["F1"]["by_condition"].items() if d["positive"]
    ]
    fig, ax = plt.subplots(figsize=(14, 5))
    x = np.arange(len(conditions))
    for offset, method in [(-0.18, "F0"), (0.18, "F1")]:
        selected = report["end_to_end"]["metrics"][method]["by_condition"]
        ax.bar(
            x + offset,
            [selected[c]["detected"] / selected[c]["positive"] for c in conditions],
            0.36,
            label=method,
        )
    ax.set_xticks(x, conditions, rotation=32, ha="right")
    ax.set(
        ylim=(0, 1.05),
        ylabel="Severity-qualified, hypothesis-matched event recall",
        title="V7 — Actual Phase 3/3.1 inputs; upstream and missing-channel failures remain misses",
    )
    ax.legend()
    png(fig, "V7_end_to_end_conditions.png")
    save(output / "figure_source_data.json", data)
    return output


def audit_and_tables(root, destination):
    report = json.loads((root / "report.json").read_text())
    destination.mkdir(parents=True, exist_ok=True)
    audit = {
        "sealed_prediction_runs": 0,
        "unconfigured_scope_green": {
            "controlled": {"F0": 0, "F1": 0},
            "end_to_end": {"F0": 0, "F1": 0},
        },
        "first_qualified_recovery_to_clear_s": {"F0": [], "F1": []},
        "repeated_open_notice_ids": {"F0": 0, "F1": 0},
        "advisory_notices": {"F0": 0, "F1": 0},
        "missing_coverage_assessments": {"F0": 0, "F1": 0},
    }
    for track in ["controlled", "end_to_end"]:
        for row in report[track]["rows"]:
            path = (
                root
                / ("controlled" if track == "controlled" else "end_to_end")
                / row["case_id"]
                / row["method"]
            )
            verify_seal(path)
            audit["sealed_prediction_runs"] += 1
            policy = json.loads((path / "policy.json").read_text())
            target = row.get("target_asset")
            # Metric rows deliberately omit source truth; the evaluator label identifies the graded scope.
            label = json.loads((path.parent / "evaluation_private/label.json").read_text())
            target = label["target_asset"]
            if not any(r["asset_id"] == target for r in policy["requirements"]):
                history = json.loads((path / "history.json").read_text())
                audit["unconfigured_scope_green"][track][row["method"]] += sum(
                    d["assessment"]["asset_id"] == target and d["assessment"]["severity"] == "green"
                    for d in history
                )
            notices = json.loads((path / "advisories.json").read_text())
            opened = Counter(n["event_id"] for n in notices if n["transition"].startswith("opened"))
            audit["repeated_open_notice_ids"][row["method"]] += sum(
                max(0, count - 1) for count in opened.values()
            )
            audit["advisory_notices"][row["method"]] += row["advisory_notices"]
            audit["missing_coverage_assessments"][row["method"]] += row.get(
                "missing_requirement_assessments", 0
            )
            # Recovery timing is censored when no qualified recovery is observed by horizon.
            events = json.loads((path / "events.json").read_text())
            for e in events:
                if (
                    e["asset_id"] == target
                    and e["hazard_id"] in ["critical-pressure", "critical-temperature"]
                    and e["lifecycle"] == "resolved"
                    and e.get("recovery_started_at")
                ):
                    audit["first_qualified_recovery_to_clear_s"][row["method"]].append(
                        (
                            datetime.fromisoformat(e["updated_at"].replace("Z", "+00:00"))
                            - datetime.fromisoformat(
                                e["recovery_started_at"].replace("Z", "+00:00")
                            )
                        ).total_seconds()
                    )
    # Seed-cluster paired comparison: conditions within each seed remain paired.
    data = report["end_to_end"]["rows"]
    seeds = sorted({r["seed"] for r in data})
    differences = []
    for seed in seeds:
        a = {r["condition"]: r for r in data if r["seed"] == seed and r["method"] == "F0"}
        b = {r["condition"]: r for r in data if r["seed"] == seed and r["method"] == "F1"}
        conditions = [c for c in a if a[c]["positive"]]
        differences.append(
            np.mean([int(b[c]["detected"]) - int(a[c]["detected"]) for c in conditions])
        )
    rng = np.random.default_rng(4001)
    samples = [
        np.mean(np.asarray(differences)[rng.integers(0, len(seeds), len(seeds))])
        for _ in range(2000)
    ]
    audit["paired_recall_difference"] = {
        "mean": float(np.mean(differences)),
        "seed_bootstrap_95": np.quantile(samples, [0.025, 0.975]).tolist(),
    }
    save(destination / "audit.json", audit)
    shutil.copy2(root / "report.json", destination / "results.json")
    fields = [
        "track",
        "condition",
        "case_id",
        "seed",
        "method",
        "positive",
        "critical",
        "detected",
        "event_matched",
        "unmatched_advisory",
        "final_severity",
        "delay_s",
        "unknown_fraction",
        "unsupported_green",
    ]
    with (destination / "trial_comparison.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for track in ["controlled", "end_to_end"]:
            for row in report[track]["rows"]:
                writer.writerow({k: row.get(k) for k in fields})
    return audit
