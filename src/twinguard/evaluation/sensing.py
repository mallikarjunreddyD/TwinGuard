"""Restricted sensor-model diagnostics only. No anomaly detection or fusion."""

from pathlib import Path
import json
import numpy as np
from twinguard.core.contracts import InspectionCapture
from twinguard.core.observations import load_public_observations, load_capture_arrays


def error_statistics(values):
    values = np.asarray(values, float)
    values = values[np.isfinite(values)]
    if not len(values):
        return {"count": 0, "rmse": None, "mean": None, "std": None, "mae": None}
    return {
        "count": len(values),
        "rmse": float(np.sqrt(np.mean(values**2))),
        "mean": float(values.mean()),
        "std": float(values.std()),
        "mae": float(np.mean(np.abs(values))),
    }


def validate_sensing_run(root: Path, write: bool = True):
    records = load_public_observations(root)
    private = root / "evaluation_private"
    installation = json.loads((private / "installation.json").read_text())
    manifest = json.loads((root / "manifest.json").read_text())
    report = {
        "validation_kind": "restricted virtual sensor model verification; no physical calibration or anomaly detection",
        "scenario_id": manifest["acquisition_namespace"],
        "fidelity": installation["fidelity"],
        "lidar": {},
        "thermal": {},
        "iot": {},
    }
    for record in records:
        if not isinstance(record, InspectionCapture):
            continue
        arrays = load_capture_arrays(root, record)
        with np.load(private / f"{record.capture_id}.npz", allow_pickle=False) as truth:
            if record.modality == "lidar":
                reported = np.asarray(record.sensor_pose.matrix)
                actual = truth["true_pose"]
                rotation = reported[:3, :3] @ actual[:3, :3].T
                report["lidar"][record.capture_id] = {
                    "emitted_rays": int(truth["emitted_ray_count"]),
                    "valid_returns": len(arrays["points_m"]),
                    "valid_return_fraction": len(arrays["points_m"])
                    / int(truth["emitted_ray_count"]),
                    "visible_ray_fraction": float(truth["visible_ray_count"])
                    / int(truth["emitted_ray_count"]),
                    "range_error_m": error_statistics(truth["range_errors_m"]),
                    "translation_error_m": float(np.linalg.norm(reported[:3, 3] - actual[:3, 3])),
                    "rotation_error_rad": float(
                        np.arccos(np.clip((np.trace(rotation) - 1) / 2, -1, 1))
                    ),
                    "actual_outlier_returns": int(truth["outliers"].sum()),
                }
            else:
                valid = arrays["valid_mask"]
                report["thermal"][record.capture_id] = {
                    "total_pixels": valid.size,
                    "valid_pixels": int(valid.sum()),
                    "valid_fraction": float(valid.mean()),
                    "apparent_model_error_c": error_statistics(
                        (arrays["temperature_c"] - truth["noiseless_apparent_c"])[valid]
                    ),
                    "surface_temperature_difference_c": error_statistics(
                        (arrays["temperature_c"] - truth["surface_temperature_c"])[valid]
                    ),
                }
    path = private / "sensor_truth.json"
    if path.exists():
        truth = json.loads(path.read_text())
        for sid in sorted({r["sensor_id"] for r in truth}):
            expected = [r for r in truth if r["sensor_id"] == sid]
            recorded = [
                r for r in records if not isinstance(r, InspectionCapture) and r.sensor_id == sid
            ]
            unique = {r.observation_id: r for r in recorded}
            attempted = {r["event_id"]: r for r in expected}
            errors = [
                r.value - attempted[r.observation_id]["noiseless_reference"]
                for r in unique.values()
            ]
            report["iot"][sid] = {
                "expected": len(expected),
                "received_messages": len(recorded),
                "unique_observations": len(unique),
                "completeness": len(unique) / len(expected),
                "measurement_error": error_statistics(errors),
                "delayed_messages": sum(r.received_at > r.acquired_at for r in recorded),
                "duplicates": sum(r.delivery_status == "duplicate" for r in recorded),
                "out_of_order": sum(r.delivery_status == "out_of_order" for r in recorded),
            }
    report["acquisition_runtime_s"] = json.loads((private / "acquisition_runtime.json").read_text())
    resource_path = private / "resource.json"
    if resource_path.exists():
        report["resource_measurement"] = json.loads(resource_path.read_text())
    if write:
        folder = root / "reports"
        folder.mkdir(exist_ok=True)
        (folder / "sensing_validation.json").write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n"
        )
        (folder / "sensing_validation.md").write_text(
            "# Virtual sensor-model validation\n\nComputed comparisons against separately stored modeled references. These are not physical sensor accuracy or anomaly detection results.\n\n```json\n"
            + json.dumps(report, indent=2)
            + "\n```\n"
        )
    return report


def attach_plant_truth(root: Path, simulator):
    """Evaluator-only replay context; the sensor reader itself never exposes faults."""
    records = load_public_observations(root)
    times = {0.0, simulator.scenario.duration_s}
    times.update(
        (r.acquired_at - simulator.scenario.simulation_start).total_seconds()
        for r in records
        if isinstance(r, InspectionCapture)
    )
    snapshots = [
        simulator.ground_truth_at(float(t), root.name).model_dump(mode="json")
        for t in sorted(times)
    ]
    payload = {
        "schema_version": "1.0.0",
        "run_id": root.name,
        "plant_config": simulator.baseline.config.model_dump(mode="json"),
        "ground_truth_snapshots": snapshots,
    }
    path = root / "evaluation_private/plant_truth.json"
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    path.chmod(0o600)
    return path
