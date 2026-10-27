"""Public-data inference entry points; predictions are persisted before evaluation."""

from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import time
import numpy as np
from .clouds import load_scan
from .registration import register
from .geometry import detect_geometry


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(data, "model_dump"):
        data = data.model_dump(mode="json")
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def fingerprint(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def seal_predictions(output, configuration, input_refs):
    files = {
        str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(output.rglob("*"))
        if path.is_file()
        and "evaluation_private" not in path.parts
        and path.name != "predictions_ready.json"
    }
    save_json(
        output / "predictions_ready.json",
        {
            "schema_version": "1.0.0",
            "prediction_id": output.name,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "configuration_sha256": fingerprint(configuration),
            "public_inputs": input_refs,
            "artifacts": files,
        },
    )


def analyze_geometry(
    baseline_path: Path,
    current_path: Path,
    configuration,
    reference,
    output: Path,
    calibration=None,
    methods=None,
):
    import open3d as o3d

    if output.exists() and any(output.iterdir()):
        raise ValueError("Prediction output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    baseline = load_scan(baseline_path, configuration)
    current = load_scan(current_path, configuration)
    reports = {}
    methods = methods or ["B1", "B2", "B3"]
    for label in methods:
        method = {"B1": "pose_only", "B2": "point_to_point", "B3": "robust_point_to_plane"}[label]
        registration, registered = register(baseline, current, configuration, reference, method)
        geometry = detect_geometry(
            baseline,
            registered,
            registration,
            reference,
            configuration,
            calibration,
            "patch_screening" if label == "B3" else "nearest_neighbor",
        )
        # Measurement time belongs to the current acquisition, not the baseline.
        geometry.acquired_at = current.record.acquired_at
        for region in geometry.regions:
            if region.legacy_detection is not None:
                region.legacy_detection.detected_at = current.record.acquired_at
        folder = output / label
        folder.mkdir()
        from twinguard.core.contracts import Artifact
        from twinguard.core.spatial import Frame

        registered_path = folder / "registered_current.npz"
        np.savez_compressed(registered_path, points_m=registered)
        registration.registered_artifact = Artifact(
            artifact_id="registered-" + label + "-" + current.record.capture_id,
            uri=str(registered_path.relative_to(output)),
            media_type="application/x-npz",
            sha256=hashlib.sha256(registered_path.read_bytes()).hexdigest(),
        )
        registration.registered_coordinate_frame = Frame(
            kind="registered_world", reference_id=baseline.record.coordinate_frame.reference_id
        )
        save_json(folder / "registration.json", registration)
        save_json(folder / "geometry.json", geometry)
        cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(registered))
        if len(registered) and not o3d.io.write_point_cloud(
            str(folder / "registered_current.ply"), cloud
        ):
            raise OSError("Registered point cloud export failed")
        np.savez_compressed(
            folder / "patches.npz",
            centers_m=np.asarray([p.center_world_m for p in geometry.patches]),
            displacement_m=np.array(
                [
                    p.displacement_m if p.displacement_m is not None else np.nan
                    for p in geometry.patches
                ]
            ),
            uncertainty_score_m=np.array(
                [
                    p.uncertainty_score_m if p.uncertainty_score_m is not None else np.nan
                    for p in geometry.patches
                ]
            ),
            significant=np.array([bool(p.significant) for p in geometry.patches]),
            valid=np.array([p.status == "valid" for p in geometry.patches]),
        )
        reports[label] = (registration, geometry)
    save_json(output / "configuration.json", configuration)
    save_json(output / "accepted_reference.json", reference)
    save_json(
        output / "calibration.json",
        calibration
        or {
            "calibration_id": "uncalibrated-prior",
            "uncertainty_floor_m": configuration.uncertainty_floor_m,
            "threshold_m": configuration.change_threshold_m,
        },
    )
    save_json(output / "runtime.json", {"runtime_s": time.perf_counter() - start})
    seal_predictions(
        output,
        configuration,
        {
            "baseline": str(baseline_path),
            "current": str(current_path),
            "baseline_payload_sha256": baseline.record.artifact.sha256,
            "current_payload_sha256": current.record.artifact.sha256,
        },
    )
    return reports


def calibrate_geometry(pairs, configuration, reference, output):
    scores = []
    residuals = []
    dataset_ids = []
    for baseline_path, current_path in pairs:
        baseline = load_scan(Path(baseline_path), configuration)
        current = load_scan(Path(current_path), configuration)
        registration, registered = register(baseline, current, configuration, reference)
        result = detect_geometry(baseline, registered, registration, reference, configuration)
        dataset_ids.append(current.record.provenance_id)
        if registration.status != "valid":
            continue
        for patch in result.patches:
            if patch.status == "valid":
                scores.append(patch.uncertainty_score_m)
                residuals.append(abs(patch.displacement_m))
    floor = (
        float(max(configuration.uncertainty_floor_m, np.quantile(residuals, 0.90)))
        if residuals
        else configuration.uncertainty_floor_m
    )
    calibration = {
        "schema_version": "1.0.0",
        "calibration_id": "geometry-"
        + hashlib.sha256(json.dumps(dataset_ids).encode()).hexdigest()[:16],
        "training_datasets": dataset_ids,
        "valid_patch_samples": len(residuals),
        "uncertainty_floor_m": floor,
        "threshold_m": configuration.change_threshold_m,
        "status": "empirical_healthy_controls" if residuals else "uncalibrated_prior",
        "interpretation": "estimated variability score; correlated patches are not independent trials; no 95 percent interval claim",
    }
    save_json(output, calibration)
    return calibration
