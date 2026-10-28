"""Privileged Phase 7 acquisition/diagnosis controller, outside production boundaries."""

from dataclasses import replace
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import json
import time
import hashlib
import numpy as np
from twinguard.analytics.config import AnalyticsConfig
from twinguard.analytics.clouds import load_scan
from twinguard.analytics.pipeline import analyze_geometry
from twinguard.analytics.geometric_improved import detect_improved
from twinguard.analytics.reference import load_reference
from twinguard.analytics.registration import apply
from twinguard.core.contracts import InspectionCapture, InspectionSchedule
from twinguard.core.observations import load_public_observations
from twinguard.core.spatial import Transform
from twinguard.inspection.visibility import look_at
from twinguard.plant.config import load_plant_config
from twinguard.plant.model import create_baseline_plant
from twinguard.plant.simulator import PlantSimulator
from twinguard.sensing.acquisition import acquire, load_installation
from .experiments import setup_scenario
from .campaigns import Campaign, resource_preflight, atomic_json


def standard_poses(root):
    install = load_installation(root / "configs/sensing/L1.yaml")
    target = np.array([0, -0.065, 1.55])
    poses = {
        "reference": install.lidar.pose,
        "original_changed": install.event_poses["lidar-01-t_60"],
    }
    for name, position in [
        ("near_left", [-0.85, 2.28, 1.25]),
        ("near_center", [0, 2.435, 1.55]),
        ("near_right", [0.85, 2.28, 1.85]),
        ("far_oblique", [1.16, 3.13, 1.55]),
    ]:
        poses[name] = look_at(np.array(position), target, "lidar-01")
    return poses


def acquire_pair(
    root,
    output,
    case_id,
    seed,
    level,
    pose,
    amplitude=0,
    profile="steady",
    baseline_pose=None,
    partial=False,
    variation=True,
):
    scenario, faults = setup_scenario(
        root,
        case_id,
        seed,
        profile=profile,
        kind="geometric" if amplitude else None,
        amplitude=amplitude,
    )
    if faults and variation:
        rng = np.random.default_rng(seed)
        faults[0].center_local_m = (
            float(rng.uniform(-0.35, 0.35)),
            0,
            float(rng.uniform(0.8, 1.55)),
        )
        faults[0].extent_m = (float(rng.uniform(0.28, 0.48)), 0.1, float(rng.uniform(0.35, 0.6)))
    install = load_installation(root / f"configs/sensing/{level}.yaml")
    if baseline_pose:
        install.lidar.pose = baseline_pose
    install.event_poses = {"lidar-01-t_60": pose}
    if partial:
        install.lidar.horizontal_fov_rad = 0.3
    scenario.inspections = [
        InspectionSchedule(sensor_id="lidar-01", offset_s=t, modality="lidar") for t in (0, 60)
    ]
    scenario.sensor_config_ids = ["lidar-01"]
    simulator = PlantSimulator(
        create_baseline_plant(load_plant_config(root / "configs/plant.yaml"), seed),
        scenario,
        faults,
    )
    acquire(simulator.sensing_reader(), scenario, install, output, modality="all")
    atomic_json(
        output / "evaluation_private/truth.json",
        simulator.ground_truth_at(60, case_id).model_dump(mode="json"),
    )
    captures = sorted(
        [
            r
            for r in load_public_observations(output)
            if isinstance(r, InspectionCapture) and r.modality == "lidar"
        ],
        key=lambda c: c.acquired_at,
    )
    return captures


def diagnose_one(task):
    root, base, case_id, seed, level, name, pose_json, amplitude = task
    root = Path(root)
    base = Path(base)
    resource_preflight(reserve_bytes=32 * 1024**2)
    path = base / "datasets" / case_id
    if path.exists():
        raise ValueError("Refuse to overwrite incomplete acquisition; use a new case identity")
    captures = acquire_pair(
        root, path, case_id, seed, level, Transform.model_validate(pose_json), amplitude
    )
    config = AnalyticsConfig()
    reference = load_reference(root / "configs/analytics/accepted_reference.json")
    cal = json.loads((root / "configs/fusion/calibration/geometry_b31.json").read_text())
    reg, actual = analyze_geometry(
        path / captures[0].artifact.uri,
        path / captures[1].artifact.uri,
        config,
        reference,
        base / "predictions" / case_id,
        methods=["B3.1"],
        improved_calibration=cal,
    )["B3.1"]
    # Predictions are sealed by analyze_geometry before this restricted evaluator opens true poses.
    from .analytics import verify_seal

    verify_seal(base / "predictions" / case_id)
    b, c = [load_scan(path / r.artifact.uri, config) for r in captures]
    poses = []
    for r in captures:
        with np.load(path / "evaluation_private" / f"{r.capture_id}.npz", allow_pickle=False) as f:
            poses.append(f["true_pose"].copy())
    relative = np.linalg.inv(poses[0]) @ poses[1]
    estimated = np.asarray(reg.transform.matrix)
    delta = apply(
        c.processing_sensor_m, np.asarray(b.record.sensor_pose.matrix) @ estimated
    ) - apply(c.processing_sensor_m, np.asarray(b.record.sensor_pose.matrix) @ relative)
    oracle_b = replace(b, processing_world_m=apply(b.processing_sensor_m, poses[0]))
    oracle_c = apply(c.processing_sensor_m, poses[1])
    oracle = detect_improved(oracle_b, oracle_c, reg, reference, config, cal)
    from twinguard.analytics.geometric_improved import measurements

    measured = measurements(
        b,
        apply(c.processing_sensor_m, np.asarray(b.record.sensor_pose.matrix) @ estimated),
        reg,
        reference,
        config,
    )
    common = [
        p.common_coverage for _, g, _, _ in measured for p in g.patches if p.asset_id == "BW-01"
    ]
    valid = [p for p in actual.patches if p.status == "valid"]
    displacements = [abs(p.displacement_m) for p in valid if p.displacement_m is not None]
    result = {
        "case_id": case_id,
        "seed": seed,
        "level": level,
        "view_group": name,
        "amplitude_m": amplitude,
        "geometry_status": actual.status,
        "actual_regions": len(actual.regions),
        "oracle_alignment_regions": len(oracle.regions),
        "oracle_scope": "Restricted alignment-only diagnostic; original registration quality gates/uncertainty retained, not production inference",
        "registration_status": reg.status,
        "registration_translation_error_m": float(
            np.linalg.norm(estimated[:3, 3] - relative[:3, 3])
        ),
        "normal_transform_error_p95_m": float(np.quantile(abs(delta[:, 1]), 0.95)),
        "rmse_m": reg.inlier_rmse_m,
        "conditioning": reg.conditioning_ratio,
        "fitness": reg.fitness,
        "median_common_patch_coverage": float(np.median(common)) if common else 0,
        "qualified_patches": len(valid),
        "patch_count": len(actual.patches),
        "normal_reference_consistency_median": float(
            np.median([abs(p.normal_world[1]) for p in valid])
        )
        if valid
        else None,
        "median_valid_patch_current_points": float(np.median([p.current_points for p in valid]))
        if valid
        else None,
        "median_valid_patch_baseline_points": float(np.median([p.baseline_points for p in valid]))
        if valid
        else None,
        "maximum_empirical_margin_m": max(
            (p.engineering_margin_m for p in valid if p.engineering_margin_m is not None),
            default=None,
        ),
        "reported_translation_std_m": captures[1].reported_translation_std_m,
        "reported_rotation_std_rad": captures[1].reported_rotation_std_rad,
        "healthy_or_fault_abs_patch_p95_m": float(np.quantile(displacements, 0.95))
        if displacements
        else None,
        "region_bounds": [r.bounds_world_m for r in actual.regions],
        "range_sigma_group": format(captures[0].acquisition_parameters["range_sigma_m"], ".6g"),
        "public_inputs": [r.capture_id for r in captures],
    }
    return result


def run_diagnostic_matrix(root, output, workers=2, smoke=False):
    poses = standard_poses(root)
    seeds = list(range(13000, 13001 if smoke else 13006))
    levels = ["L1"] if smoke else ["L0", "L1", "L2"]
    amplitudes = [0, 0.02]
    tasks = []
    for seed in seeds:
        for level in levels:
            for name, pose in poses.items():
                for amplitude in amplitudes:
                    ident = f"v7diag-{len(tasks):05d}"
                    tasks.append(
                        (
                            str(root),
                            str(output),
                            ident,
                            seed,
                            level,
                            name,
                            pose.model_dump(mode="json"),
                            amplitude,
                        )
                    )
    configuration = {
        "purpose": "Phase7 fresh controlled viewpoint diagnostic matrix",
        "seeds": seeds,
        "levels": levels,
        "amplitudes": amplitudes,
        "requested_poses": {k: v.model_dump(mode="json") for k, v in poses.items()},
        "workers": workers,
        "count": len(tasks),
        "model_sha256": hashlib.sha256(
            (root / "configs/fusion/calibration/geometry_b31.json").read_bytes()
        ).hexdigest(),
    }
    campaign = Campaign(
        output, configuration, reserve_bytes=min(len(tasks) * 5 * 1024**2, 2 * 1024**3)
    )
    started = time.perf_counter()
    try:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for result in pool.map(diagnose_one, tasks):
                campaign.commit(result["case_id"], result)
                print(
                    result["case_id"],
                    result["level"],
                    result["view_group"],
                    result["actual_regions"],
                    result["oracle_alignment_regions"],
                    flush=True,
                )
        campaign.finish(len(tasks))
        rows = [json.loads(p.read_text()) for p in sorted((output / "cases").glob("*.json"))]
        atomic_json(
            output / "report.json",
            {
                "status": "executed",
                "count": len(rows),
                "elapsed_s": time.perf_counter() - started,
                "rows": rows,
            },
        )
        return rows
    except BaseException as exc:
        campaign.fail(exc)
        raise
