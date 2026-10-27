"""Restricted paired evaluation, including failures and excluded displacement estimates."""

import json
import numpy as np
from .analytics import summarize_e1, classification, wilson, verify_seal
from .geometric_studies import private_context, patch_truth
from twinguard.core.analytics_contracts import PatchEstimate


def enrich(data, output, rows, trial):
    verify_seal(output)
    _, _, fault = private_context(data)
    for row in rows:
        geometry = json.loads((output / row["method"] / "geometry.json").read_text())
        qualified = []
        unqualified = []
        raw = []
        missing = 0
        for value in geometry["patches"]:
            p = PatchEstimate.model_validate(value)
            radius, true = patch_truth(p, fault)
            if p.asset_id != "BW-01" or radius > 1:
                continue
            if p.displacement_m is None:
                missing += 1
                continue
            error = p.displacement_m - true
            (qualified if p.status == "valid" else unqualified).append(error)
            raw.append(
                (p.raw_displacement_m if p.raw_displacement_m is not None else p.displacement_m)
                - true
            )
        row.update(
            seed=trial["seed"],
            qualified_signed_errors_m=qualified,
            unqualified_signed_errors_m=unqualified,
            raw_signed_errors_m=raw,
            missing_roi_estimates=missing,
            registered_prediction_coverage=geometry["status"] == "valid",
            measurement_basis=geometry.get("measurement_basis", "absolute"),
        )
    return rows


def error_stats(values):
    return {
        "count": len(values),
        "mae_mm": float(np.mean(np.abs(values)) * 1000) if values else None,
        "rmse_mm": float(np.sqrt(np.mean(np.array(values) ** 2)) * 1000) if values else None,
        "bias_mm": float(np.mean(values) * 1000) if values else None,
    }


def subset_summary(rows):
    d = classification(rows)
    d["qualified_trials"] = sum(r["registered_prediction_coverage"] for r in rows)
    d["prediction_coverage"] = d["qualified_trials"] / max(len(rows), 1)
    d["conditional_detection"] = classification(
        [r for r in rows if r["registered_prediction_coverage"]]
    )
    d["registration_failures"] = sum(not r["registration_valid"] for r in rows)
    d["mean_translation_error_mm"] = float(np.mean([r["translation_error_mm"] for r in rows]))
    d["mean_rotation_error_deg"] = float(np.mean([r["rotation_error_deg"] for r in rows]))
    d["mean_pipeline_runtime_s"] = float(
        np.mean([r["registration_runtime_s"] + r["geometry_runtime_s"] for r in rows])
    )
    for field in [
        "qualified_signed_errors_m",
        "unqualified_signed_errors_m",
        "raw_signed_errors_m",
    ]:
        d[field] = error_stats([v for r in rows for v in r[field]])
    d["missing_roi_estimates"] = sum(r["missing_roi_estimates"] for r in rows)
    d["recall_wilson_95"] = wilson(d["true_positive"], d["positive_trials"])
    d["fpr_wilson_95"] = wilson(d["false_positive"], d["negative_trials"])
    return d


def summarize(rows):
    result = summarize_e1(rows)
    for method, details in result.items():
        selected = [r for r in rows if r["method"] == method]
        details["complete_case_accounting"] = subset_summary(selected)
        details["fidelity_amplitude"] = {
            level: {
                str(int(a * 1000)): subset_summary(
                    [
                        r
                        for r in selected
                        if r["fidelity"] == level
                        and r["amplitude_m"] == a
                        and r["viewpoint"] in ["same", "changed"]
                    ]
                )
                for a in [0, 0.01, 0.02, 0.03, 0.05]
            }
            for level in ["L0", "L1", "L2"]
        }
        details["by_viewpoint"] = {
            v: subset_summary([r for r in selected if r["viewpoint"] == v])
            for v in sorted({r["viewpoint"] for r in selected})
        }
    return result


def paired_bootstrap(rows, repetitions=2000):
    baseline = {
        r["case_id"]: r
        for r in rows
        if r["method"] == "B3" and r["viewpoint"] in ["same", "changed"]
    }
    improved = {
        r["case_id"]: r
        for r in rows
        if r["method"] == "B3.1" and r["viewpoint"] in ["same", "changed"]
    }
    seeds = sorted({r["seed"] for r in baseline.values()})
    rng = np.random.default_rng(3101)
    deltas = []
    for seed in seeds:
        cases = [k for k, r in baseline.items() if r["seed"] == seed]
        positives = [k for k in cases if baseline[k]["positive"]]
        negatives = [k for k in cases if not baseline[k]["positive"]]
        deltas.append(
            [
                np.mean(
                    [int(improved[k]["detected"]) - int(baseline[k]["detected"]) for k in positives]
                ),
                np.mean(
                    [int(improved[k]["detected"]) - int(baseline[k]["detected"]) for k in negatives]
                ),
                np.mean(
                    [
                        int(improved[k]["status"] != "valid")
                        - int(baseline[k]["status"] != "valid")
                        for k in cases
                    ]
                ),
            ]
        )
    values = np.asarray(deltas)
    boot = np.array(
        [values[rng.integers(0, len(seeds), len(seeds))].mean(0) for _ in range(repetitions)]
    )
    return {
        name: {
            "difference": float(values[:, i].mean()),
            "seed_cluster_bootstrap_95": np.quantile(boot[:, i], [0.025, 0.975]).tolist(),
        }
        for i, name in enumerate(["recall", "healthy_fpr", "inconclusive_fraction"])
    }
