"""Post-inference metrics. This module alone accesses private sensor/plant labels."""

from pathlib import Path
import hashlib
import json
import numpy as np
from .observability import deformation_audit


def verify_seal(output):
    path = output / "predictions_ready.json"
    if not path.is_file():
        raise ValueError("Predictions must be saved before evaluation")
    seal = json.loads(path.read_text())
    for name, digest in seal["artifacts"].items():
        if hashlib.sha256((output / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Prediction modified after inference")
    return seal


def rate(n, d):
    return n / d if d else None


def classification(rows):
    tp = sum(r["positive"] and r["detected"] for r in rows)
    fp = sum(not r["positive"] and r["detected"] for r in rows)
    positives = sum(r["positive"] for r in rows)
    negatives = len(rows) - positives
    return {
        "trials": len(rows),
        "positive_trials": positives,
        "negative_trials": negatives,
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": positives - tp,
        "true_negative": negatives - fp,
        "precision": rate(tp, tp + fp),
        "recall": rate(tp, positives),
        "false_positive_rate": rate(fp, negatives),
    }


def wilson(success, total):
    if not total:
        return None
    z = 1.96
    p = success / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    half = z * np.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return [float(max(0, center - half)), float(min(1, center + half))]


def evaluate_e1(data: Path, predictions: Path, trial):
    seal = verify_seal(predictions)
    audit = deformation_audit(data)
    private = predictions / "evaluation_private"
    private.mkdir(exist_ok=True, mode=0o700)
    private.chmod(0o700)
    (private / "observability.json").write_text(json.dumps(audit, indent=2) + "\n")
    (private / "observability.json").chmod(0o600)
    manifest = json.loads((data / "manifest.json").read_text())
    refs = [r for r in manifest["observations"] if "/lidar/" in r["record_uri"]]
    refs.sort(key=lambda r: json.loads((data / r["record_uri"]).read_text())["acquired_at"])
    baseline, current = [json.loads((data / r["record_uri"]).read_text()) for r in refs]
    with (
        np.load(
            data / "evaluation_private" / f"{baseline['capture_id']}.npz", allow_pickle=False
        ) as a,
        np.load(
            data / "evaluation_private" / f"{current['capture_id']}.npz", allow_pickle=False
        ) as b,
    ):
        true = np.linalg.inv(a["true_pose"]) @ b["true_pose"]
        sensor_rmse = [float(np.sqrt(np.mean(s["range_errors_m"] ** 2))) for s in [a, b]]
    context = json.loads((data / "evaluation_private/plant_truth.json").read_text())
    truth_state = context["ground_truth_snapshots"][-1]["fault_states"]
    fault = next(
        (
            f["configuration"]
            for f in truth_state
            if f["category"]
            in ("localized_geometric_deformation", "structural_support_displacement")
        ),
        None,
    )
    positive = trial["amplitude_m"] != 0 or trial.get("support", False)
    rows = []
    for method in [name for name in ("B1", "B2", "B3", "B3.1") if (predictions / name).is_dir()]:
        registration = json.loads((predictions / method / "registration.json").read_text())
        geometry = json.loads((predictions / method / "geometry.json").read_text())
        estimated = np.asarray(registration["transform"]["matrix"])
        rotation = estimated[:3, :3] @ true[:3, :3].T
        errors = []
        uncertainty_covered = []
        localized = False
        matched_regions = 0
        centroid_errors = []
        for region in geometry["regions"]:
            center = (np.asarray(region["bounds_world_m"][0]) + region["bounds_world_m"][1]) / 2
            if trial.get("support"):
                matched = region["asset_id"] == "SUP-01"
                distance = None
            else:
                # Audit ROI is defined before testing and never handed to the detector.
                local = center - np.array([0, 0, 0.35])
                roi = audit["roi"]
                r2 = ((local[0] - roi["center_local_m"][0]) / roi["extent_m"][0]) ** 2 + (
                    (local[2] - roi["center_local_m"][2]) / roi["extent_m"][2]
                ) ** 2
                matched = region["asset_id"] == "BW-01" and r2 <= 1
                distance = np.linalg.norm(local[[0, 2]] - np.asarray(roi["center_local_m"])[[0, 2]])
            localized |= matched
            matched_regions += int(matched and positive)
            if matched and distance is not None:
                centroid_errors.append(float(distance))
        if positive and not trial.get("support"):
            for patch in geometry["patches"]:
                if patch["status"] != "valid" or patch["asset_id"] != "BW-01":
                    continue
                center = np.asarray(patch["center_world_m"]) - np.array([0, 0, 0.35])
                roi = audit["roi"]
                r2 = ((center[0] - roi["center_local_m"][0]) / roi["extent_m"][0]) ** 2 + (
                    (center[2] - roi["center_local_m"][2]) / roi["extent_m"][2]
                ) ** 2
                if r2 > 1:
                    continue
                true_displacement = trial["amplitude_m"] * max(0, 1 - r2) ** 3
                error = abs(patch["displacement_m"] - true_displacement)
                errors.append(error)
                uncertainty_covered.append(bool(error <= 1.5 * patch["uncertainty_score_m"]))
        valid = registration["status"] == "valid" and geometry["status"] == "valid"
        # Inconclusive positive cases remain in overall recall denominator.
        detected = bool(geometry["regions"]) if not positive else bool(localized and valid)
        rows.append(
            {
                "case_id": trial["case_id"],
                "method": method,
                "fidelity": trial["fidelity"],
                "viewpoint": trial["viewpoint"],
                "amplitude_m": trial["amplitude_m"],
                "positive": positive,
                "detected": detected,
                "any_region": bool(geometry["regions"]),
                "true_localized_regions": matched_regions,
                "false_localized_regions": len(geometry["regions"]) - matched_regions,
                "status": geometry["status"],
                "registration_valid": registration["status"] == "valid",
                "translation_error_mm": float(
                    np.linalg.norm(estimated[:3, 3] - true[:3, 3]) * 1000
                ),
                "rotation_error_deg": float(
                    np.degrees(np.arccos(np.clip((np.trace(rotation) - 1) / 2, -1, 1)))
                ),
                "fitness": registration["fitness"],
                "inlier_rmse_m": registration["inlier_rmse_m"],
                "observable": None if trial.get("support") else audit["pair_observable"],
                "fault_kind": "support" if trial.get("support") else "water_wall",
                "valid_patch_fraction": sum(p["status"] == "valid" for p in geometry["patches"])
                / max(1, len(geometry["patches"])),
                "displacement_errors_m": errors,
                "engineering_score_covered": uncertainty_covered,
                "localization_errors_m": centroid_errors,
                "sensor_range_rmse_m": sensor_rmse,
                "prediction_configuration_sha256": seal["configuration_sha256"],
                "registration_runtime_s": registration["runtime_s"],
                "geometry_runtime_s": geometry["runtime_s"],
                "fault_configuration_available": fault is not None,
            }
        )
    (private / "metrics.json").write_text(json.dumps(rows, indent=2) + "\n")
    (private / "metrics.json").chmod(0o600)
    return rows


def summarize_e1(rows):
    result = {}
    for method in sorted({r["method"] for r in rows}):
        subset = [r for r in rows if r["method"] == method]
        overall = classification(subset)
        errors = [e for r in subset for e in r["displacement_errors_m"]]
        covered = [e for r in subset for e in r["engineering_score_covered"]]
        overall.update(
            registration_failure_fraction=sum(not r["registration_valid"] for r in subset)
            / len(subset),
            inconclusive_fraction=sum(r["status"] != "valid" for r in subset) / len(subset),
            translation_error_mm_mean=float(np.mean([r["translation_error_mm"] for r in subset])),
            rotation_error_deg_mean=float(np.mean([r["rotation_error_deg"] for r in subset])),
            displacement_mae_mm=float(np.mean(errors) * 1000) if errors else None,
            displacement_rmse_mm=float(np.sqrt(np.mean(np.asarray(errors) ** 2)) * 1000)
            if errors
            else None,
            qualified_patch_error_count=len(errors),
            engineering_score_empirical_coverage=float(np.mean(covered)) if covered else None,
            observable_only=classification([r for r in subset if r["observable"]]),
            recall_wilson_95=wilson(overall["true_positive"], overall["positive_trials"]),
            fpr_wilson_95=wilson(overall["false_positive"], overall["negative_trials"]),
            mean_registration_runtime_s=float(
                np.mean([r["registration_runtime_s"] for r in subset])
            ),
        )
        healthy_valid = [r for r in subset if not r["positive"] and r["status"] == "valid"]
        overall["negative_inconclusive_trials"] = sum(
            not r["positive"] and r["status"] != "valid" for r in subset
        )
        overall["qualified_healthy_false_positive_rate"] = rate(
            sum(r["detected"] for r in healthy_valid), len(healthy_valid)
        )
        overall["qualified_healthy_trials"] = len(healthy_valid)
        overall["event_precision"] = overall["precision"]
        true_regions = sum(r["true_localized_regions"] for r in subset)
        false_regions = sum(r["false_localized_regions"] for r in subset)
        overall["region_precision"] = rate(true_regions, true_regions + false_regions)
        overall["precision"] = overall["region_precision"]
        overall["region_true_positive"] = true_regions
        overall["region_false_positive"] = false_regions
        localization = [e for r in subset for e in r["localization_errors_m"]]
        overall["mean_region_centroid_localization_error_m"] = (
            float(np.mean(localization)) if localization else None
        )
        overall["by_fidelity"] = {
            level: classification([r for r in subset if r["fidelity"] == level])
            for level in sorted({r["fidelity"] for r in subset})
        }
        overall["by_amplitude_mm"] = {
            str(int(amp * 1000)): classification(
                [r for r in subset if r["amplitude_m"] == amp and r["fault_kind"] != "support"]
            )
            for amp in sorted({r["amplitude_m"] for r in subset})
        }
        result[method] = overall
    return result


def thermal_summary(rows):
    result = classification(rows)
    result["inconclusive_fraction"] = sum(r["status"] != "valid" for r in rows) / max(len(rows), 1)
    result["mean_valid_pixel_fraction"] = (
        float(np.mean([r["valid_pixels"] / r["total_pixels"] for r in rows])) if rows else None
    )
    result["saturated_pixel_fraction"] = sum(r["saturated_pixels"] for r in rows) / max(
        sum(r["total_pixels"] for r in rows), 1
    )
    localization = [
        r["intersection_over_union"]
        for r in rows
        if r["positive"] and r["intersection_over_union"] is not None
    ]
    residual = [
        r["visible_anomaly_residual_mae_c"]
        for r in rows
        if r["visible_anomaly_residual_mae_c"] is not None
    ]
    result["positive_mean_iou"] = float(np.mean(localization)) if localization else None
    result["qualified_positive_residual_mae_c"] = float(np.mean(residual)) if residual else None
    return result
