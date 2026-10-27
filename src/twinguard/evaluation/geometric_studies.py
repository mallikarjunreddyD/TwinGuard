"""Restricted Phase 3.1 diagnostic tools. Never imported by production analytics."""

from dataclasses import replace
import json
import time
import hashlib
import subprocess
import numpy as np
from scipy.spatial import cKDTree
from twinguard.analytics.config import AnalyticsConfig
from twinguard.analytics.clouds import load_scan
from twinguard.analytics.registration import register, apply
from twinguard.analytics.geometry import detect_geometry
from twinguard.analytics.reference import load_reference, mask_asset
from twinguard.analytics.pipeline import save_json, analyze_geometry
from twinguard.core.observations import load_public_observations
from twinguard.core.contracts import InspectionCapture, InspectionSchedule
from twinguard.plant.config import load_plant_config
from twinguard.plant.model import create_baseline_plant
from twinguard.plant.simulator import PlantSimulator
from twinguard.sensing.acquisition import acquire, load_installation
from twinguard.evaluation.sensing import attach_plant_truth
from twinguard.evaluation.experiments import setup_scenario
from twinguard.evaluation.observability import deformation_audit


def generate(root, output, case_id, seed, level, amplitude, view, component=None, variation=0):
    """Controller-only: preserve first-hit physics and existing noise distributions."""
    scenario, faults = setup_scenario(
        root, case_id, seed, kind="geometric" if amplitude else None, amplitude=amplitude
    )
    if variation and faults:
        faults[0].center_local_m = (
            -0.10 if variation % 2 else 0.10,
            0,
            1.10 if variation % 3 else 1.30,
        )
        faults[0].extent_m = (0.35 if variation % 2 else 0.45, 0.1, 0.45 if variation % 3 else 0.55)
    installation = load_installation(root / f"configs/sensing/{level}.yaml")
    if component:
        nominal = load_installation(root / "configs/sensing/L1.yaml")
        if component == "range":
            installation.lidar.noise.sigma = nominal.lidar.noise.sigma
            installation.lidar.noise.range_slope = nominal.lidar.noise.range_slope
        elif component == "pose":
            installation.lidar.pose_error = nominal.lidar.pose_error.model_copy(deep=True)
        elif component == "dropout":
            installation.lidar.noise.dropout = nominal.lidar.noise.dropout
            installation.lidar.noise.incidence_dropout = nominal.lidar.noise.incidence_dropout
    if view == "same":
        installation.event_poses = {}
    elif view == "partial":
        installation.lidar.horizontal_fov_rad = 0.25
        installation.lidar.pose.matrix[0][3] = -0.8
        installation.event_poses = {}
    elif view == "high_pose":
        installation.lidar.pose_error.translation_sigma_m = 0.2
        installation.lidar.pose_error.rotation_sigma_rad = 0.06
    elif view == "low_overlap":
        pose = installation.lidar.pose.model_copy(deep=True)
        pose.matrix[0][3] = 4
        installation.event_poses = {"lidar-01-t_60": pose}
    scenario.inspections = [
        InspectionSchedule(sensor_id=installation.lidar.sensor_id, offset_s=t, modality="lidar")
        for t in [0, 60]
    ]
    scenario.sensor_config_ids = [installation.lidar.sensor_id]
    simulator = PlantSimulator(
        create_baseline_plant(load_plant_config(root / "configs/plant.yaml"), seed),
        scenario,
        faults,
    )
    acquire(simulator.sensing_reader(), scenario, installation, output, modality="all")
    attach_plant_truth(output, simulator)
    return capture_paths(output)


def capture_paths(data):
    records = sorted(
        [
            r
            for r in load_public_observations(data)
            if isinstance(r, InspectionCapture) and r.modality == "lidar"
        ],
        key=lambda r: r.acquired_at,
    )
    return [data / r.artifact.uri for r in records]


def private_context(data):
    captures = capture_paths(data)
    records = [load_scan(p, AnalyticsConfig()).record for p in captures]
    poses = []
    for r in records:
        with np.load(data / "evaluation_private" / f"{r.capture_id}.npz") as f:
            poses.append(f["true_pose"].copy())
    truth = json.loads((data / "evaluation_private/plant_truth.json").read_text())
    faults = truth["ground_truth_snapshots"][-1]["fault_states"]
    fault = next(
        (f["configuration"] for f in faults if f["category"] == "localized_geometric_deformation"),
        None,
    )
    return records, poses, fault


def patch_truth(patch, fault):
    center = np.asarray(patch.center_world_m) - [0, 0, 0.35]
    roi = fault or {"center_local_m": [0, 0, 1.2], "extent_m": [0.4, 0.1, 0.5]}
    radius = sum(((center[k] - roi["center_local_m"][k]) / roi["extent_m"][k]) ** 2 for k in [0, 2])
    amp = (fault or {}).get("true_displacement_m") or 0
    return radius, amp * max(0, 1 - radius) ** 3


def trace(
    data, label, config, reference, calibration, registration=None, current=None, oracle=False
):
    start = time.perf_counter()
    paths = capture_paths(data)
    b, c = [load_scan(p, config) for p in paths]
    records, poses, fault = private_context(data)
    if registration is None:
        registration, current = register(b, c, config, reference)
    original_status = registration.status
    # Raw estimates remain diagnostic-only even if quality would prevent production inference.
    measured_registration = registration.model_copy(update={"status": "valid"})
    if oracle:
        b = replace(b, processing_world_m=apply(b.processing_sensor_m, poses[0]))
        current = apply(c.processing_sensor_m, poses[1])
    geometry = detect_geometry(b, current, measured_registration, reference, config, calibration)
    true_relative = np.linalg.inv(poses[0]) @ poses[1]
    estimated = np.asarray(registration.transform.matrix)
    rotation = estimated[:3, :3] @ true_relative[:3, :3].T
    error_world = apply(
        c.processing_sensor_m, np.asarray(records[0].sensor_pose.matrix) @ estimated
    ) - apply(c.processing_sensor_m, np.asarray(records[0].sensor_pose.matrix) @ true_relative)
    normal_error = error_world[:, 1] if len(error_world) else np.array([np.nan])
    patches = []
    for p in geometry.patches:
        radius, truth = patch_truth(p, fault)
        if p.asset_id != "BW-01":
            continue
        raw = p.displacement_m
        patches.append(
            {
                **p.model_dump(mode="json"),
                "inside_roi": bool(radius <= 1),
                "true_center_displacement_m": truth,
                "signed_error_m": None if raw is None else raw - truth,
                "T1_fixed": raw is not None and abs(raw) > config.change_threshold_m,
                "T2_original": p.significant is True,
                "T3_candidate": None,
            }
        )
    relevant = [p for p in patches if p["inside_roi"] and p["displacement_m"] is not None]
    audit = deformation_audit(data)
    minimum = min((r["valid_region_returns"] for r in audit["captures"]), default=0)
    common = audit["common_observed_cell_fraction"]
    coverage = (
        "fully_occluded"
        if minimum == 0
        else "insufficient"
        if minimum < 12 or common < 0.1
        else "marginal"
        if common < 0.25
        else "adequate"
    )
    errors = [p["signed_error_m"] for p in relevant]
    return {
        "label": label,
        "oracle": oracle,
        "amplitude_m": (fault or {}).get("true_displacement_m") or 0,
        "point_counts": [len(b.original_sensor_m), len(c.original_sensor_m)],
        "processed_point_counts": [len(b.processing_sensor_m), len(c.processing_sensor_m)],
        "registration": registration.model_dump(mode="json"),
        "registration_status": original_status,
        "translation_error_m": 0
        if oracle
        else float(np.linalg.norm(estimated[:3, 3] - true_relative[:3, 3])),
        "rotation_error_deg": 0
        if oracle
        else float(np.degrees(np.arccos(np.clip((np.trace(rotation) - 1) / 2, -1, 1)))),
        "normal_registration_error_median_m": 0 if oracle else float(np.median(normal_error)),
        "normal_registration_error_p95_m": 0
        if oracle
        else float(np.quantile(np.abs(normal_error), 0.95)),
        "patches": patches,
        "relevant_usable_patches": len(relevant),
        "raw_roi_mae_m": float(np.mean(np.abs(errors))) if errors else None,
        "raw_roi_bias_m": float(np.mean(errors)) if errors else None,
        "max_raw_roi_m": max([abs(p["displacement_m"]) for p in relevant], default=None),
        "candidate_regions": len(geometry.regions),
        "regions": [r.model_dump(mode="json") for r in geometry.regions],
        "status_with_diagnostic_gate_override": geometry.status,
        "coverage_category": coverage,
        "audit": audit,
        "processing_time_s": time.perf_counter() - start,
    }


def diagnostics(root, output, baseline):
    output.mkdir(parents=True, exist_ok=False)
    config = AnalyticsConfig()
    reference = load_reference(root / "configs/analytics/accepted_reference.json")
    calibration = json.loads((baseline / "geometry_calibration.json").read_text())
    rows = []
    conditions = [
        ("ideal-same", "L0", "same", None),
        ("ideal-changed", "L0", "changed", None),
        ("range-only", "L0", "same", "range"),
        ("pose-only", "L0", "same", "pose"),
        ("dropout-only", "L0", "same", "dropout"),
        ("nominal", "L1", "changed", None),
        ("degraded", "L2", "changed", None),
    ]
    for seed in range(1100, 1104):
        for amplitude in [0, 0.01, 0.02, 0.03, 0.05]:
            for condition, level, view, component in conditions:
                case = f"diag-{len(rows):04d}"
                data = output / "datasets" / case
                generate(root, data, case, seed, level, amplitude, view, component)
                predictions = output / "predictions" / case
                analyze_geometry(*capture_paths(data), config, reference, predictions, calibration)
                actual = trace(data, condition, config, reference, calibration)
                oracle = trace(data, condition, config, reference, calibration, oracle=True)
                row = {
                    "case_id": case,
                    "seed": seed,
                    "condition": condition,
                    "level": level,
                    "view": view,
                    "amplitude_m": amplitude,
                    "actual": actual,
                    "oracle": oracle,
                    "scales": {},
                    "registration_variants": {},
                }
                # D4 below/near/above the compact field core; fixed before diagnostics.
                if condition in ["ideal-same", "nominal"]:
                    for radius in [0.08, 0.12, 0.18, 0.28]:
                        variant = config.model_copy(update={"patch_radius_m": radius})
                        row["scales"][str(radius)] = trace(
                            data, condition, variant, reference, calibration, oracle=True
                        )
                    b, c = [load_scan(p, config) for p in capture_paths(data)]
                    # D6 explicit all-surface robust and strict stable-only geometry.
                    no_stable = reference.model_copy(
                        update={
                            "assets": [
                                a.model_copy(update={"stable": False}) for a in reference.assets
                            ]
                        }
                    )
                    all_config = config.model_copy(update={"monitored_assets": []})
                    for method in ["point_to_point", "robust_point_to_plane"]:
                        reg, points = register(b, c, all_config, no_stable, method)
                        row["registration_variants"][method + "-all"] = trace(
                            data, condition, config, reference, calibration, reg, points
                        )
                    masks = []
                    for cloud in [b, c]:
                        mask = np.zeros(len(cloud.processing_world_m), bool)
                        for a in reference.assets:
                            if a.stable:
                                mask |= mask_asset(cloud.processing_world_m, a, config.roi_margin_m)
                        masks.append(mask)
                    reg, _ = register(
                        replace(
                            b,
                            processing_world_m=b.processing_world_m[masks[0]],
                            processing_sensor_m=b.processing_sensor_m[masks[0]],
                        ),
                        replace(
                            c,
                            processing_world_m=c.processing_world_m[masks[1]],
                            processing_sensor_m=c.processing_sensor_m[masks[1]],
                        ),
                        all_config,
                        no_stable,
                        "robust_point_to_plane",
                    )
                    row["registration_variants"]["strict-stable-only"] = {
                        "registration": reg.model_dump(mode="json"),
                        "anchor_counts": [int(m.sum()) for m in masks],
                    }
                save_json(output / "restricted_traces" / f"{case}.json", row)
                rows.append(
                    {
                        "case_id": case,
                        "seed": seed,
                        "condition": condition,
                        "amplitude_m": amplitude,
                        "actual_mae_m": actual["raw_roi_mae_m"],
                        "oracle_mae_m": oracle["raw_roi_mae_m"],
                    }
                )
                if len(rows) % 10 == 0:
                    print("diagnostics", len(rows), flush=True)
    save_json(output / "index.json", rows)
    save_json(
        output / "metadata.json",
        {
            "source_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True
            ).strip(),
            "configuration": config.model_dump(mode="json"),
            "calibration": calibration,
            "source_hashes": {
                str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in [
                    root / "src/twinguard/analytics/geometry.py",
                    root / "src/twinguard/analytics/registration.py",
                ]
            },
        },
    )
    return rows


def roi_sampling(data, fault):
    """Restricted sampling measurements, not production coverage inputs."""
    result = []
    roi = fault or {"center_local_m": [0, 0, 1.2], "extent_m": [0.4, 0.1, 0.5]}
    for path in capture_paths(data):
        with np.load(data / "evaluation_private" / f"{path.stem}.npz") as f:
            points = f["surface_world_m"]
            local = points - [0, 0, 0.35]
            r2 = sum(
                ((local[:, k] - roi["center_local_m"][k]) / roi["extent_m"][k]) ** 2 for k in [0, 2]
            )
            subset = points[(f["asset_ids"] == "BW-01") & (r2 <= 1)]
            inside = (f["asset_ids"] == "BW-01") & (r2 <= 1)
            nearest = (
                cKDTree(subset[:, [0, 2]]).query(subset[:, [0, 2]], k=2)[0][:, 1]
                if len(subset) > 1
                else []
            )
            ray = points - f["true_pose"][:3, 3]
            incidence = np.abs(ray[:, 1]) / np.maximum(np.linalg.norm(ray, axis=1), 1e-12)
            result.append(
                {
                    "valid_returns": len(subset),
                    "peak_core_returns": int(((r2 <= 0.1) & (f["asset_ids"] == "BW-01")).sum()),
                    "nearest_tangent_spacing_median_m": float(np.median(nearest))
                    if len(nearest)
                    else None,
                    "wall_prior_incidence_cosine_median": float(np.median(incidence[inside]))
                    if inside.any()
                    else None,
                    "true_triangle_incidence": "not retained in existing private artifacts",
                }
            )
    return result
