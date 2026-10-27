from pathlib import Path
import json
import numpy as np
from twinguard.evaluation.geometric_studies import trace, roi_sampling, private_context
from twinguard.analytics.config import AnalyticsConfig
from twinguard.analytics.reference import load_reference
from twinguard.analytics.pipeline import save_json

root = Path.cwd()
run = root / "experiments/outputs/phase3_1/baseline-reproduction"
out = root / "experiments/outputs/phase3_1/baseline-traces"
out.mkdir(exist_ok=True)
config = AnalyticsConfig()
reference = load_reference(root / "configs/analytics/accepted_reference.json")
calibration = json.loads((run / "geometry_calibration.json").read_text())
healthy = []
for d in sorted((run / "datasets").glob("calibration-*")):
    t = trace(d, "healthy-calibration", config, reference, calibration)
    healthy.append(
        max(
            [abs(p["displacement_m"]) for p in t["patches"] if p["displacement_m"] is not None],
            default=0,
        )
    )
threshold = float(np.quantile(healthy, 0.95))
rows = []
report = json.loads((run / "report.json").read_text())
for original in [r for r in report["rows"] if r["method"] == "B3"]:
    case = original["case_id"]
    data = run / "datasets" / case
    t = trace(data, "original-E1", config, reference, calibration)
    _, _, fault = private_context(data)
    t["sampling"] = roi_sampling(data, fault)
    for p in t["patches"]:
        p["T3_candidate"] = p["displacement_m"] is not None and abs(p["displacement_m"]) > threshold
    t["original_evaluation"] = original
    t["T3_healthy_trialmax_threshold_m"] = threshold
    causes = []
    relevant = [p for p in t["patches"] if p["inside_roi"] and p["displacement_m"] is not None]
    if original["positive"] and not original["detected"]:
        if t["coverage_category"] in ["insufficient", "fully_occluded"]:
            causes.append("coverage")
        if t["registration_status"] != "valid":
            causes.append("registration_quality_gate")
        if not relevant:
            causes.append("neighborhood_qualification")
        if (
            relevant
            and max(abs(p["displacement_m"]) for p in relevant) <= config.change_threshold_m
        ):
            causes.append("raw_below_absolute_threshold")
        if any(p["T1_fixed"] for p in relevant) and not any(p["T2_original"] for p in relevant):
            causes.append("uncertainty_penalty")
        if any(p["T2_original"] for p in relevant) and not t["regions"]:
            causes.append("region_minimum_cluster")
        if t["regions"] and not original["detected"]:
            causes.append("localization_or_global_quality")
        if not causes:
            causes.append("unresolved")
    t["supported_contributors"] = causes
    t["earliest_limiting_stage"] = next(
        (
            c
            for c in [
                "coverage",
                "registration_quality_gate",
                "neighborhood_qualification",
                "raw_below_absolute_threshold",
                "uncertainty_penalty",
                "region_minimum_cluster",
                "localization_or_global_quality",
                "unresolved",
            ]
            if c in causes
        ),
        None,
    )
    save_json(out / f"{case}.json", t)
    rows.append(
        {
            "case_id": case,
            "amplitude_m": original["amplitude_m"],
            "fidelity": original["fidelity"],
            "detected": original["detected"],
            "causes": causes,
            "earliest": t["earliest_limiting_stage"],
            "coverage": t["coverage_category"],
            "normal_error_p95_m": t["normal_registration_error_p95_m"],
            "T1_patches": sum(p["T1_fixed"] for p in relevant),
            "T2_patches": sum(p["T2_original"] for p in relevant),
            "T3_patches": sum(p["T3_candidate"] for p in relevant),
        }
    )
    if len(rows) % 20 == 0:
        print("baseline traces", len(rows), flush=True)
save_json(
    out / "summary.json",
    {"rows": rows, "healthy_trial_maxima_m": healthy, "T3_threshold_m": threshold},
)
