"""Derived Phase7 metrics; incomplete journals never become complete validation claims."""

from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
from collections import Counter
import numpy as np
from twinguard.core.observations import load_public_observations
from twinguard.core.contracts import SensorObservation

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/phase7"
BASE = ROOT / "experiments/outputs"


def load(path):
    return json.loads(path.read_text())


def save(path, value):
    path.write_text(json.dumps(value, indent=2, default=str, allow_nan=False) + "\n")


def rows(name, detector=False):
    directory = BASE / name
    journal = load(directory / "campaign.json")
    result = []
    for ident, checksum in journal["completed"].items():
        p = directory / "cases" / (ident + ".json")
        if hashlib.sha256(p.read_bytes()).hexdigest() != checksum:
            raise ValueError("Checkpoint checksum mismatch: " + str(p))
        data = load(p)
        result.extend(data["rows"] if detector else data)
    return journal, result


def ratio(data, numerator, denominator):
    n = sum(numerator(r) for r in data)
    d = sum(denominator(r) for r in data)
    return n / d if d else None


def clustered(data, numerator, denominator):
    seeds = sorted({r["seed"] for r in data})
    sums = np.array(
        [
            [
                sum(numerator(r) for r in data if r["seed"] == s),
                sum(denominator(r) for r in data if r["seed"] == s),
            ]
            for s in seeds
        ],
        float,
    )
    rng = np.random.default_rng(77029)
    boots = sums[rng.integers(0, len(seeds), (2000, len(seeds)))].sum(axis=1)
    estimates = boots[boots[:, 1] > 0, 0] / boots[boots[:, 1] > 0, 1]
    return {
        "estimate": ratio(data, numerator, denominator),
        "cluster_seeds": len(seeds),
        "bootstrap_replicates": 2000,
        "ci95": np.quantile(estimates, [0.025, 0.975]).tolist() if len(estimates) else None,
    }


def detector_summary():
    journal, data = rows("phase7-V3-heldout-detectors", True)
    result = {
        "status": journal["status"],
        "pairs": len(journal["completed"]),
        "source_configuration_hash": journal["configuration_hash"],
        "methods": {},
    }
    for method in ("B3.1", "B3.2"):
        rr = [r for r in data if r["method"] == method]
        groups = {}
        for level in ("all", "L0", "L1", "L2"):
            subset = rr if level == "all" else [r for r in rr if r["level"] == level]
            groups[level] = {
                "scans": len(subset),
                "healthy": sum(not r["fault_present"] for r in subset),
                "faults": sum(r["fault_present"] for r in subset),
                "localized_recall": clustered(
                    subset,
                    lambda r: r["localized_detected"] and r["fault_present"],
                    lambda r: r["fault_present"],
                ),
                "healthy_fpr": clustered(
                    subset,
                    lambda r: r["positive"] and not r["fault_present"],
                    lambda r: not r["fault_present"],
                ),
                "region_precision": clustered(
                    subset, lambda r: r["matched_regions"], lambda r: r["regions"]
                ),
                "inconclusive": sum(r["status"] != "valid" for r in subset),
                "registration_failures": sum(r["registration_status"] != "valid" for r in subset),
                "calibration_applicable": sum(r["calibration_applicable"] for r in subset),
                "positive_regions": sum(r["regions"] for r in subset),
                "matched_regions": sum(r["matched_regions"] for r in subset),
            }
        result["methods"][method] = groups
    supported = {
        r["case_id"] for r in data if r["method"] == "B3.2" and r["calibration_applicable"]
    }
    result["same_supported_domain_subset"] = {}
    for method in ("B3.1", "B3.2"):
        rr = [r for r in data if r["method"] == method and r["case_id"] in supported]
        result["same_supported_domain_subset"][method] = {
            "scans": len(rr),
            "faults": sum(r["fault_present"] for r in rr),
            "localized_detected": sum(r["localized_detected"] for r in rr),
            "healthy": sum(not r["fault_present"] for r in rr),
            "healthy_positive": sum(r["positive"] and not r["fault_present"] for r in rr),
            "inconclusive": sum(r["status"] != "valid" for r in rr),
            "localized_recall": clustered(
                rr,
                lambda r: r["localized_detected"] and r["fault_present"],
                lambda r: r["fault_present"],
            ),
            "healthy_fpr": clustered(
                rr,
                lambda r: r["positive"] and not r["fault_present"],
                lambda r: not r["fault_present"],
            ),
        }
    result["same_supported_domain_subset_scope"] = (
        "Descriptive identical public applicability domains, not an overall improvement or random sample of all views; global abstention/recall remain primary."
    )
    save(OUT / "heldout_detector_summary.json", result)
    return result


def planner_summary():
    journal, data = rows("phase7-V3-heldout-planners")
    result = {
        "status": journal["status"],
        "cases": len(journal["completed"]),
        "expected_cases": journal["configuration"]["count"],
        "source_configuration_hash": journal["configuration_hash"],
        "methods": {},
    }
    if journal["status"] == "completed":
        for detector in ("B3.1", "B3.2"):
            for method in ("P0", "P1", "P2", "P3", "P3v2"):
                rr = [r for r in data if r["detector"] == detector and r["method"] == method]
                result["methods"][detector + " / " + method] = {
                    "trials": len(rr),
                    "views": sum(r["views"] for r in rr),
                    "initial_recall": clustered(
                        rr,
                        lambda r: r["amplitude_m"] > 0 and r["initial_localized"],
                        lambda r: r["amplitude_m"] > 0,
                    ),
                    "new_recall": clustered(
                        rr,
                        lambda r: r["amplitude_m"] > 0 and r["new_localized"],
                        lambda r: r["amplitude_m"] > 0,
                    ),
                    "cumulative_recall": clustered(
                        rr,
                        lambda r: r["amplitude_m"] > 0 and r["cumulative_localized"],
                        lambda r: r["amplitude_m"] > 0,
                    ),
                    "additional_recall": clustered(
                        rr,
                        lambda r: (
                            r["amplitude_m"] > 0
                            and not r["initial_localized"]
                            and r["new_localized"]
                        ),
                        lambda r: r["amplitude_m"] > 0 and not r["initial_localized"],
                    ),
                    "confirmation_recall": clustered(
                        rr,
                        lambda r: (
                            r["amplitude_m"] > 0 and r["initial_localized"] and r["new_localized"]
                        ),
                        lambda r: r["amplitude_m"] > 0 and r["initial_localized"],
                    ),
                    "region_precision": clustered(
                        rr, lambda r: r["matched_regions"], lambda r: r["positive_regions"]
                    ),
                    "healthy_false_positive": clustered(
                        rr,
                        lambda r: r["amplitude_m"] == 0 and r["healthy_false_positive"],
                        lambda r: r["amplitude_m"] == 0,
                    ),
                    "inconclusive": sum(r["inconclusive"] for r in rr),
                    "reg_failures": sum(r["registration_failures"] for r in rr),
                    "new_qualified_area_total_m2": sum(r["new_qualified_area_m2"] for r in rr),
                    "useful_fault_views_proxy": sum(
                        r["new_localized"] and r["amplitude_m"] > 0 for r in rr
                    ),
                    "fault_yield_per_view": ratio(
                        rr,
                        lambda r: r["new_localized"] and r["amplitude_m"] > 0,
                        lambda r: r["views"],
                    ),
                    "fault_yield_per_mission_proxy_min": ratio(
                        rr,
                        lambda r: r["new_localized"] and r["amplitude_m"] > 0,
                        lambda r: r["mission_proxy_s"] / 60,
                    ),
                    "mission_proxy_s_total": sum(r["mission_proxy_s"] for r in rr),
                    "compute_wall_s_total": sum(r["wall_s"] for r in rr),
                    "compute_cpu_s_total": sum(r["cpu_s"] for r in rr),
                    "peak_rss_kib": max(r["rss_peak_kib"] for r in rr),
                }
    else:
        result["limitation"] = (
            "Resource-stopped partial sample; no headline performance comparison or confidence intervals until all predeclared paired cases finish."
        )
    save(OUT / "heldout_planner_summary.json", result)
    aj, ab = rows("phase7-V3-acquisition-ablations")
    summary = {"status": aj["status"], "cases": len(aj["completed"]), "groups": {}}
    for detector in ("B3.1", "B3.2"):
        for name in sorted({r["ablation"] for r in ab}):
            rr = [r for r in ab if r["detector"] == detector and r["ablation"] == name]
            summary["groups"][detector + " / " + name] = {
                "trials": len(rr),
                "views": sum(r["views"] for r in rr),
                "new_localized": sum(r["new_localized"] for r in rr),
                "initial_localized": sum(r["initial_localized"] for r in rr),
                "inconclusive": sum(r["inconclusive"] for r in rr),
                "new_area_m2": sum(r["new_qualified_area_m2"] for r in rr),
                "actual_initial_acquisitions_per_trial": 2,
                "interpretation": "Zero selected views imply an uninformative reinspection ablation even though fresh initial sensing was executed",
            }
    save(OUT / "acquisition_ablation_summary.json", summary)
    return result, summary


def percentiles(values):
    return {
        "n": len(values),
        **{
            key: float(np.percentile(values, q)) if values else None
            for key, q in [("p50", 50), ("p95", 95), ("p99", 99), ("max", 100)]
        },
    }


def stamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def operational(name, critical_seeds):
    directory = Path(name) if Path(name).is_absolute() else BASE / name
    label = directory.name
    records = load(directory / "records.json")
    observations = {r["id"]: r for r in load(directory / "observations.json")}
    timing = {r["id"]: r["body"] for r in records if r["kind"] == "timing"}
    traces = {r["id"]: r["body"] for r in records if r["kind"] == "trace"}
    expected = {}
    for pub in directory.rglob("publisher.json"):
        manifest = load(pub)
        path = Path(manifest["dataset"])
        if not any(path.name == f"e4-public-{seed}" for seed in critical_seeds):
            continue
        public = {
            r.observation_id: r
            for r in load_public_observations(path)
            if isinstance(r, SensorObservation)
        }
        for message in manifest["messages"]:
            ident = message.get("observation_id")
            obs = public.get(ident)
            if (
                obs
                and obs.sensor_id == "pressure-01"
                and obs.quality == "good"
                and obs.value >= 1150000
            ):
                expected[ident] = message
    rows = []
    for ident, message in expected.items():
        row = {
            "observation_id": ident,
            "publisher_emitted_at": message["emitted_at"],
            "mapped_acquired_at": message["effective_acquired_at"],
            "state": "missed",
            "receipt_to_advisory_s": None,
        }
        o = observations.get(ident)
        t = timing.get(ident)
        if o and t:
            trace = next(
                (
                    traces[i]
                    for i in t.get("assessments", [])
                    if i in traces and traces[i]["assessment"]["asset_id"] == "BW-01"
                ),
                None,
            )
            if trace:
                temporal = [
                    d["status"]
                    for d in trace["temporal"]
                    if d["evidence_id"] == "limit-" + ident
                    and d["hazard_id"] == "critical-pressure"
                ]
                row["state"] = temporal[0] if temporal else "missed"
                row["receipt_to_advisory_s"] = stamp(t["advisory_commit_confirmed_at"]) - stamp(
                    o["received"]
                )
                row["mapped_acquisition_to_advisory_s"] = stamp(
                    t["advisory_commit_confirmed_at"]
                ) - stamp(message["effective_acquired_at"])
                row["severity"] = trace["assessment"]["severity"]
        rows.append(row)
    counts = dict(Counter(r["state"] for r in rows))
    report = load(directory / "report.json")
    result = {
        "campaign": name,
        "status": report.get("status", "executed"),
        "started_at": report["started_at"],
        "finished_at": report["finished_at"],
        "critical_expected_published": len(rows),
        "critical_states": counts,
        "receipt_to_advisory_s": percentiles(
            [r["receipt_to_advisory_s"] for r in rows if r["receipt_to_advisory_s"] is not None]
        ),
        "critical_rows": rows,
        "all_expected_current": len(rows) > 0 and counts.get("current", 0) == len(rows),
    }
    if "profiles" in report:
        result["recovery"] = [r for r in report["profiles"] if r.get("service")]
        result["completeness_profiles"] = [
            {
                k: r[k]
                for k in ("profile", "seed", "published", "persisted", "completeness")
                if k in r
            }
            for r in report["profiles"]
            if "completeness" in r
        ]
        result["concurrent_planning"] = dict(
            Counter(
                r.get("status", r.get("error", "unknown"))
                for r in report.get("concurrent_planning", [])
            )
        )
        result["browser"] = report.get("browser", {}).get("checks")
        result["jobs_final"] = report.get("jobs_final")
        result["api_latency_s"] = percentiles(
            [s["api_latency_s"] for s in report["samples"] if "api_latency_s" in s]
        )
    save(OUT / (label.replace("phase7-", "") + "-summary.json"), result)
    return result


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    detector_summary()
    planner_summary()
    operational("phase7-V4-full-E4-recovery-retest", [8210, 8211, 8212])
    operational("phase7-V4-backlog-critical", [18010, 18011, 18012])
    save(
        OUT / "summary_revision.json",
        {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        },
    )
    print("Derived summaries saved; incomplete planner evidence remains explicitly incomplete.")
