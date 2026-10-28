"""Restricted post-seal diagnosis of frozen E5 healthy views; no baseline metric replacement."""

from pathlib import Path
import json
import time
import numpy as np
from scipy.spatial import cKDTree
from twinguard.evaluation.campaigns import Campaign
from twinguard.evaluation.analytics import verify_seal
from twinguard.analytics.clouds import load_scan
from twinguard.analytics.config import AnalyticsConfig
from twinguard.analytics.registration import apply
from twinguard.core.observations import load_public_observations
from twinguard.core.contracts import InspectionCapture

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/outputs/phase7-V1-E5-diagnosis"


def main():
    campaign = Campaign(
        OUT,
        {
            "purpose": "Restricted diagnosis of E5 healthy changed-view behavior",
            "source": "a283713",
            "seeds": list(range(11100, 11130)),
            "scenario": "E5-S01",
            "method": "P0/P1/P2/P3",
            "metrics_rule": "Diagnostic outputs only; old E5 trial tables remain unchanged",
        },
        resume=False,
        reserve_bytes=100 * 1024**2,
    )
    started = time.perf_counter()
    try:
        for seed in range(11100, 11130):
            trial = ROOT / f"experiments/outputs/phase6-E5-recovered/shard-0/E5-S01-{seed}"
            initial = sorted(
                [
                    c
                    for c in load_public_observations(trial / "initial")
                    if isinstance(c, InspectionCapture) and c.modality == "lidar"
                ],
                key=lambda c: c.acquired_at,
            )
            baseline = load_scan(trial / "initial" / initial[0].artifact.uri, AnalyticsConfig())
            with np.load(
                trial / "initial/evaluation_private" / f"{initial[0].capture_id}.npz",
                allow_pickle=False,
            ) as values:
                base_true = values["true_pose"].copy()
            rows = []
            for method in ("P0", "P1", "P2", "P3"):
                work = trial / method
                verify_seal(work)
                plan = json.loads((work / "plan.json").read_text())
                results = json.loads((work / "results.json").read_text())
                for index, result in enumerate(results):
                    if "analysis" not in result:
                        continue
                    data = work / f"view-{index}"
                    capture = next(
                        c
                        for c in load_public_observations(data)
                        if isinstance(c, InspectionCapture)
                    )
                    current = load_scan(data / capture.artifact.uri, AnalyticsConfig())
                    reg = result["registration"]
                    geo = result["analysis"]
                    # Restricted evaluator reads true pose only after public result seal verification.
                    with np.load(
                        data / "evaluation_private" / f"{capture.capture_id}.npz",
                        allow_pickle=False,
                    ) as values:
                        current_true = values["true_pose"].copy()
                    relative = np.linalg.inv(base_true) @ current_true
                    estimate = np.asarray(reg["transform"]["matrix"])
                    rotation = estimate[:3, :3] @ relative[:3, :3].T
                    reported_base = np.asarray(baseline.record.sensor_pose.matrix)
                    estimated_points = apply(current.processing_sensor_m, reported_base @ estimate)
                    true_points = apply(current.processing_sensor_m, reported_base @ relative)
                    normal_error = estimated_points[:, 1] - true_points[:, 1]
                    residuals = cKDTree(baseline.processing_world_m).query(estimated_points)[0]
                    candidate = next(
                        v for v in plan["candidates"] if v["viewpoint_id"] == result["viewpoint_id"]
                    )
                    patches = geo["patches"]
                    valid = [p for p in patches if p["status"] == "valid"]
                    margins = [
                        p["engineering_margin_m"]
                        for p in valid
                        if p["engineering_margin_m"] is not None
                    ]
                    signed = [p["displacement_m"] for p in valid if p["displacement_m"] is not None]
                    rows.append(
                        {
                            "seed": seed,
                            "method": method,
                            "viewpoint_id": candidate["viewpoint_id"],
                            "geometry_positive": bool(geo["significant"]),
                            "regions": len(geo["regions"]),
                            "geometry_status": geo["status"],
                            "registration_status": reg["status"],
                            "registration_translation_error_m": float(
                                np.linalg.norm(estimate[:3, 3] - relative[:3, 3])
                            ),
                            "registration_rotation_error_rad": float(
                                np.arccos(np.clip((np.trace(rotation) - 1) / 2, -1, 1))
                            ),
                            "normal_registration_error_p95_m": float(
                                np.quantile(abs(normal_error), 0.95)
                            ),
                            "public_nn_residual_p95_m": float(np.quantile(residuals, 0.95)),
                            "estimated_registration_rmse_m": reg["inlier_rmse_m"],
                            "conditioning": reg["conditioning_ratio"],
                            "fitness": reg["fitness"],
                            "view_separation_m": float(
                                np.linalg.norm(
                                    np.asarray(capture.sensor_pose.matrix)[:3, 3]
                                    - reported_base[:3, 3]
                                )
                            ),
                            "expected_range_m": candidate["expected_range_m"],
                            "expected_incidence_cosine": candidate["incidence_cosine_mean"],
                            "sampling_spacing_proxy_m": candidate["predicted_spacing_m"],
                            "predicted_quality": candidate["expected_quality"],
                            "valid_patch_count": len(valid),
                            "patch_count": len(patches),
                            "patch_displacement_median_m": float(np.median(signed))
                            if signed
                            else None,
                            "patch_abs_displacement_p95_m": float(
                                np.quantile(abs(np.asarray(signed)), 0.95)
                            )
                            if signed
                            else None,
                            "maximum_empirical_margin_m": max(margins, default=None),
                            "significant_patch_count": sum(
                                p["significant"] is True for p in patches
                            ),
                            "calibration_id": geo["calibration_id"],
                            "calibration_selection_group": format(
                                initial[0].acquisition_parameters["range_sigma_m"], ".6g"
                            ),
                            "actual_qualified_area_m2": result["coverage"]["qualified_area_m2"],
                            "region_bounds": [r["bounds_world_m"] for r in geo["regions"]],
                            "scope": "True-pose error is restricted diagnosis only; incidence/spacing are accepted-map public proxies; no causal attribution percentage inferred",
                        }
                    )
            campaign.commit(str(seed), {"rows": rows})
        campaign.finish(30)
        rows = [
            r
            for path in sorted((OUT / "cases").glob("*.json"))
            for r in json.loads(path.read_text())["rows"]
        ]
        summary = {}
        for method in ("P0", "P1", "P2", "P3"):
            values = [r for r in rows if r["method"] == method]
            positives = [r for r in values if r["geometry_positive"]]
            summary[method] = {
                "actual_scans": len(values),
                "positive_scans": len(positives),
                "positive_region_count": sum(r["regions"] for r in values),
                "median_normal_registration_p95_m": float(
                    np.median([r["normal_registration_error_p95_m"] for r in values])
                ),
                "median_healthy_abs_patch_p95_m": float(
                    np.median(
                        [
                            r["patch_abs_displacement_p95_m"]
                            for r in values
                            if r["patch_abs_displacement_p95_m"] is not None
                        ]
                    )
                ),
                "median_reported_view_separation_m": float(
                    np.median([r["view_separation_m"] for r in values])
                ),
                "calibration_groups": sorted({r["calibration_selection_group"] for r in values}),
            }
        report = {
            "status": "executed",
            "summary": summary,
            "rows": rows,
            "elapsed_s": time.perf_counter() - started,
        }
        from twinguard.evaluation.campaigns import atomic_json

        atomic_json(OUT / "report.json", report)
        atomic_json(ROOT / "docs/phase7/V1_E5_diagnostics.json", report)
        print(json.dumps(summary, indent=2), flush=True)
    except BaseException as exc:
        campaign.fail(exc)
        raise


if __name__ == "__main__":
    main()
