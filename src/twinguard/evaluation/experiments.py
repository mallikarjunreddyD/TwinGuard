"""Privileged reproducible dataset controller and post-inference experiment orchestration."""

from pathlib import Path
import json
import time
import resource
import subprocess
from datetime import timedelta
import numpy as np
import yaml
from twinguard.core.contracts import (
    ScenarioDefinition,
    InspectionSchedule,
    OperatingPoint,
    InspectionCapture,
)
from twinguard.core.observations import load_public_observations
from twinguard.plant.config import load_plant_config
from twinguard.plant.model import create_baseline_plant
from twinguard.plant.simulator import PlantSimulator
from twinguard.evaluation.contracts import FaultInjection
from twinguard.sensing.acquisition import acquire, load_installation
from twinguard.evaluation.sensing import attach_plant_truth
from twinguard.analytics.config import load_config
from twinguard.analytics.reference import load_reference
from twinguard.analytics.pipeline import (
    analyze_geometry,
    calibrate_geometry,
    save_json,
    fingerprint,
    seal_predictions,
)
from twinguard.analytics.operating import calibrate_operating, infer_operating, measured_records
from twinguard.analytics.thermal import calibrate_thermal, infer_thermal
from .analytics import thermal_summary, evaluate_e1, summarize_e1, verify_seal, classification


def setup_scenario(root, case_id, seed, profile="steady", kind=None, amplitude=0.03):
    raw = yaml.safe_load((root / "scenarios/S0.yaml").read_text())
    raw["scenario_id"] = case_id
    raw["random_seed"] = seed
    raw["fault_config_references"] = []
    raw["dataset"]["dataset_id"] = "dataset-" + case_id
    raw["description"] = "Controlled experiment source, not an analytics label"
    scenario = ScenarioDefinition.model_validate(raw)
    if profile == "increase":
        scenario.operating_profile = [
            OperatingPoint(offset_s=0, normalized_load=0.5, operating_mode="load_transition"),
            OperatingPoint(offset_s=60, normalized_load=0.8),
        ]
    if profile == "decrease":
        scenario.operating_profile = [
            OperatingPoint(offset_s=0, normalized_load=0.8, operating_mode="load_transition"),
            OperatingPoint(offset_s=60, normalized_load=0.3),
        ]
    if profile == "mismatch":
        scenario.operating_profile = [OperatingPoint(offset_s=0, normalized_load=0.95)]
    faults = []
    if kind:
        category = {
            "geometric": "localized_geometric_deformation",
            "support": "structural_support_displacement",
            "thermal": "thermal_hotspot",
            "process": "abnormal_process_measurement",
        }[kind]
        parameters = dict(
            fault_id="fault-" + case_id,
            asset_id="SUP-01" if kind == "support" else "BW-01",
            category=category,
            start_at=scenario.simulation_start + timedelta(seconds=30),
            end_at=scenario.simulation_start + timedelta(seconds=90),
            severity_parameters={},
            affected_region_id="surface",
            ground_truth_artifacts=[],
            evolution="linear" if kind == "geometric" else "step",
            growth_duration_s=30 if kind == "geometric" else 0,
            persistence="persistent" if kind in ("geometric", "support") else "recover",
            recovery_duration_s=10 if kind in ("thermal", "process") else 0,
        )
        if kind == "geometric":
            parameters["true_displacement_m"] = amplitude
        if kind == "support":
            parameters["displacement_vector_m"] = (0.02, 0, 0)
        if kind in ("thermal", "process"):
            parameters["true_process_deviation"] = 12 if kind == "thermal" else 200000
            parameters["deviation_unit"] = "degC" if kind == "thermal" else "Pa"
        faults = [FaultInjection.model_validate(parameters)]
    scenario.fault_config_references = [f.fault_id for f in faults]
    return scenario, faults


def generate_case(
    root,
    output,
    case_id,
    seed,
    level="L1",
    amplitude=0.0,
    viewpoint="changed",
    profile="steady",
    kind=None,
    e2=False,
):
    scenario, faults = setup_scenario(
        root, case_id, seed, profile, kind or ("geometric" if amplitude else None), amplitude
    )
    installation = load_installation(root / f"configs/sensing/{level}.yaml")
    if viewpoint == "same":
        installation.event_poses = {}
    if viewpoint == "partial":
        installation.lidar.horizontal_fov_rad = 0.25
        installation.lidar.pose.matrix[0][3] = -0.8
        installation.event_poses = {}
    if viewpoint == "high_pose":
        installation.lidar.pose_error.translation_sigma_m = 0.2
        installation.lidar.pose_error.rotation_sigma_rad = 0.06
    if viewpoint == "low_overlap":
        import copy

        pose = copy.deepcopy(installation.lidar.pose)
        pose.matrix[0][3] = 4
        installation.event_poses = {"lidar-01-t_60": pose}
    if e2:
        scenario.inspections = [
            InspectionSchedule(
                sensor_id=installation.thermal.sensor_id, offset_s=t, modality="thermal"
            )
            for t in [0, 30, 60, 90, 120]
        ]
        if kind == "degradation":
            raise ValueError("Sensor degradation is an acquisition setting, not a plant fault")
        if profile == "degraded":
            installation.thermal.measurement_max_c = 80
            for sensor in installation.iot:
                sensor.delivery.dropout = 0.35
                sensor.delivery.delay_jitter_s = 8
                if sensor.source == "pressure":
                    sensor.noise.bias = 20000
    else:
        scenario.inspections = [
            InspectionSchedule(sensor_id=installation.lidar.sensor_id, offset_s=t, modality="lidar")
            for t in [0, 60]
        ]
        scenario.sensor_config_ids = [installation.lidar.sensor_id]
    baseline = create_baseline_plant(load_plant_config(root / "configs/plant.yaml"), seed)
    simulator = PlantSimulator(baseline, scenario, faults)
    if e2 and profile == "degraded":
        # A healthy physical plant with explicitly impaired instruments.
        pass
    acquire(simulator.sensing_reader(), scenario, installation, output, modality="all")
    attach_plant_truth(output, simulator)
    if not e2:
        records = [r for r in load_public_observations(output) if isinstance(r, InspectionCapture)]
        return [output / r.artifact.uri for r in sorted(records, key=lambda r: r.acquired_at)]
    return output


def run_e1(root: Path, output: Path, benchmark):
    if output.exists() and any(output.iterdir()):
        raise ValueError("Experiment output must be new/empty")
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    config = load_config(root / benchmark["analytics_config"])
    reference = load_reference(root / benchmark["accepted_reference"])
    save_json(output / "benchmark.json", benchmark)
    save_json(output / "algorithm.json", config)
    calibration_pairs = []
    for seed in benchmark["calibration_seeds"]:
        name = f"calibration-{seed}"
        pair = generate_case(root, output / "datasets" / name, name, seed, "L1", 0.0, "changed")
        calibration_pairs.append(pair)
    calibration = calibrate_geometry(
        calibration_pairs, config, reference, output / "geometry_calibration.json"
    )
    frozen = fingerprint({"algorithm": config.model_dump(mode="json"), "calibration": calibration})
    rows = []
    cases = []
    for seed in benchmark["evaluation_seeds"]:
        for level in benchmark["fidelities"]:
            for amplitude in benchmark["amplitudes_m"]:
                for view in benchmark["viewpoints"]:
                    cases.append(
                        dict(
                            case_id=f"e1-{seed}-{level}-{int(amplitude * 1000)}-{view}",
                            seed=seed,
                            fidelity=level,
                            amplitude_m=amplitude,
                            viewpoint=view,
                        )
                    )
    for index, view in enumerate(benchmark.get("robustness_viewpoints", [])):
        cases.append(
            dict(
                case_id=f"robust-{view}",
                seed=900 + index,
                fidelity="L2",
                amplitude_m=0.03,
                viewpoint=view,
            )
        )
    if benchmark.get("include_support"):
        cases.append(
            dict(
                case_id="support-control",
                seed=990,
                fidelity="L1",
                amplitude_m=0.0,
                viewpoint="changed",
                support=True,
            )
        )
    for index, trial in enumerate(cases):
        trial["case_id"] = f"e1-trial-{index:04d}"
        data = output / "datasets" / trial["case_id"]
        pair = generate_case(
            root,
            data,
            trial["case_id"],
            trial["seed"],
            trial["fidelity"],
            trial["amplitude_m"],
            trial["viewpoint"],
            kind="support" if trial.get("support") else None,
        )
        predictions = output / "predictions" / trial["case_id"]
        analyze_geometry(pair[0], pair[1], config, reference, predictions, calibration)
        if (
            fingerprint({"algorithm": config.model_dump(mode="json"), "calibration": calibration})
            != frozen
        ):
            raise RuntimeError("Algorithm/calibration changed during held-out testing")
        rows.extend(evaluate_e1(data, predictions, trial))
        if index % 10 == 0:
            print(f"E1 {index + 1}/{len(cases)}", flush=True)
    result = {
        "experiment_id": "E1",
        "software_version": __import__("twinguard").__version__,
        "configuration": benchmark,
        "frozen_algorithm_calibration_sha256": frozen,
        "calibration": calibration,
        "trial_count": len(cases),
        "rows": rows,
        "metrics": summarize_e1(rows),
        "runtime_s": time.perf_counter() - started,
        "process_peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        "git_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip(),
        "statistical_note": "Wilson intervals describe this controlled mixture, not industrial generalization; repeated patch errors are correlated",
    }
    save_json(output / "report.json", result)
    return result


def infer_e2_case(data, output, model, model_dir, config, reference):
    output.mkdir(parents=True, exist_ok=False)
    records = measured_records(data)
    for method in ["static", "conditioned", "conditioned_quality"]:
        predictions = infer_operating(records, model, config, method)
        save_json(
            output / f"operating-{method}.json", [p.model_dump(mode="json") for p in predictions]
        )
    thermal = []
    for record in load_public_observations(data):
        if not isinstance(record, InspectionCapture) or record.modality != "thermal":
            continue
        for method in ["static", "conditioned"]:
            result, arrays = infer_thermal(data, record, model_dir, config, reference, method)
            folder = output / method
            folder.mkdir(exist_ok=True)
            save_json(folder / (record.capture_id + ".json"), result)
            np.savez_compressed(folder / (record.capture_id + ".npz"), **arrays)
            thermal.append(result)
    seal_predictions(
        output,
        config,
        {
            "public_dataset": str(data),
            "operating_model": model["model_id"],
            "thermal_model": str(model_dir),
        },
    )
    return thermal


def evaluate_e2(data, output, group):
    verify_seal(output)
    from datetime import datetime
    from twinguard.evaluation.contracts import FaultInjection
    from twinguard.plant.faults import factor_at

    context = json.loads((data / "evaluation_private/plant_truth.json").read_text())
    faults = [
        FaultInjection.model_validate(f["configuration"])
        for f in context["ground_truth_snapshots"][0]["fault_states"]
    ]
    metrics = {}
    for method in ["static", "conditioned", "conditioned_quality"]:
        predictions = json.loads((output / f"operating-{method}.json").read_text())
        trials = []
        normal_errors = []
        latencies = []
        for p in predictions:
            timestamp = datetime.fromisoformat(p["acquired_at"].replace("Z", "+00:00"))
            positive = False
            for f in faults:
                factor = factor_at(f, timestamp)
                if (
                    f.category == "abnormal_process_measurement"
                    and p["unit"] == "Pa"
                    and factor * abs(f.true_process_deviation or 0) >= 1000
                ):
                    positive = True
                if (
                    f.category == "thermal_hotspot"
                    and p["sensor_id"] == "wall-thermometer"
                    and factor * abs(f.true_process_deviation or 0) >= 1
                ):
                    positive = True
            significant = p["significant"] is True and p["status"] == "valid"
            trials.append(dict(positive=positive, detected=significant, status=p["status"]))
            if not positive and p["residual"] is not None:
                normal_errors.append(p["residual"])
            if positive and significant:
                first = min(f.start_at for f in faults)
                latencies.append(max(0, (timestamp - first).total_seconds()))
        score = classification(trials)
        score.update(
            group=group,
            inconclusive_fraction=sum(p["status"] != "valid" for p in predictions)
            / max(len(predictions), 1),
            out_of_range_fraction=sum(p["status"] == "out_of_reference_range" for p in predictions)
            / max(len(predictions), 1),
            normal_residual_rmse_by_unit={
                unit: float(
                    np.sqrt(
                        np.mean(
                            [
                                p["residual"] ** 2
                                for p, t in zip(predictions, trials)
                                if not t["positive"]
                                and p["unit"] == unit
                                and p["residual"] is not None
                            ]
                        )
                    )
                )
                for unit in sorted({p["unit"] for p in predictions})
                if any(
                    not t["positive"] and p["unit"] == unit and p["residual"] is not None
                    for p, t in zip(predictions, trials)
                )
            },
            first_detection_delay_s=min(latencies) if latencies else None,
            normal_error_count=len(normal_errors),
        )
        metrics[method] = score
    thermal_metrics = []
    # Full hidden temperatures are replayed only after prediction seal verification.
    from twinguard.sensing.raycast import RayScene
    from twinguard.sensing.thermal import camera_directions, apparent_temperature
    from twinguard.sensing.config import ThermalConfig

    installation = json.loads((data / "evaluation_private/installation.json").read_text())
    camera = ThermalConfig.model_validate(installation["thermal"])
    scenario = ScenarioDefinition.model_validate_json(
        (data / "evaluation_private/scenario.json").read_text()
    )
    plant = load_plant_config_from_dict(context["plant_config"])
    physical = PlantSimulator(create_baseline_plant(plant, scenario.random_seed), scenario, faults)
    healthy = PlantSimulator(create_baseline_plant(plant, scenario.random_seed), scenario, [])
    for capture in load_public_observations(data):
        if not isinstance(capture, InspectionCapture) or capture.modality != "thermal":
            continue
        t = (capture.acquired_at - scenario.simulation_start).total_seconds()
        with np.load(
            data / "evaluation_private" / f"{capture.capture_id}.npz", allow_pickle=False
        ) as truth:
            pose = truth["true_pose"]
        directions, _ = camera_directions(camera)
        world = directions @ pose[:3, :3].T
        current_scene = RayScene(physical.sensing_reader().read_at(t))
        baseline_scene = RayScene(healthy.sensing_reader().read_at(t))
        current_hits = current_scene.cast(pose[:3, 3], world)
        base_hits = baseline_scene.cast(pose[:3, 3], world)
        current_temp = current_scene.temperature(current_hits)
        base_temp = baseline_scene.temperature(base_hits)
        delta = apparent_temperature(
            current_temp, camera.emissivity, camera.reflected_temperature_c
        ) - apparent_temperature(base_temp, camera.emissivity, camera.reflected_temperature_c)
        true_mask = (np.isfinite(delta) & (delta >= 1)).reshape(camera.height, camera.width)
        for method in ["static", "conditioned"]:
            result = json.loads((output / method / (capture.capture_id + ".json")).read_text())
            with np.load(
                output / method / (capture.capture_id + ".npz"), allow_pickle=False
            ) as arrays:
                predicted = arrays["candidate_mask"]
                valid = arrays["quantitative_mask"]
                intersection = int((predicted & true_mask).sum())
                union = int((predicted | true_mask).sum())
                positive = bool(true_mask.sum() >= 4)
                detected = bool(
                    result["significant"]
                    and result["status"] == "valid"
                    and (intersection >= 4 if positive else True)
                )
                errors = arrays["residual_c"].ravel() - delta
                mask = valid.ravel() & np.isfinite(errors) & true_mask.ravel()
                thermal_metrics.append(
                    {
                        "method": method,
                        "capture_id": capture.capture_id,
                        "positive": positive,
                        "detected": detected,
                        "status": result["status"],
                        "true_visible_pixels": int(true_mask.sum()),
                        "valid_pixels": result["valid_pixels"],
                        "saturated_pixels": result["saturated_pixels"],
                        "total_pixels": result["total_pixels"],
                        "intersection_over_union": intersection / union if union else None,
                        "visible_anomaly_residual_mae_c": float(np.mean(np.abs(errors[mask])))
                        if mask.any()
                        else None,
                    }
                )
    summary = {"operating": metrics, "thermal": thermal_metrics, "group": group}
    private = output / "evaluation_private"
    private.mkdir(mode=0o700, exist_ok=True)
    save_json(private / "metrics.json", summary)
    (private / "metrics.json").chmod(0o600)
    return summary


def load_plant_config_from_dict(raw):
    from twinguard.plant.config import PlantConfig

    return PlantConfig.model_validate(raw)


def run_e2(root, output, benchmark):
    if output.exists() and any(output.iterdir()):
        raise ValueError("Experiment output must be empty")
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    config = load_config(root / benchmark["analytics_config"])
    reference = load_reference(root / benchmark["accepted_reference"])
    calibration = []
    for seed in benchmark["calibration_seeds"]:
        for profile in ["steady", "increase", "decrease"]:
            name = f"healthy-{seed}-{profile}"
            calibration.append(
                generate_case(
                    root, output / "calibration" / name, name, seed, profile=profile, e2=True
                )
            )
    model = calibrate_operating(calibration, config)
    model_dir = output / "models"
    model_dir.mkdir()
    save_json(model_dir / "operating_model.json", model)
    calibrate_thermal(calibration, model, config, model_dir)
    frozen = fingerprint({"configuration": config.model_dump(mode="json"), "model": model})
    rows = []
    for seed in benchmark["evaluation_seeds"]:
        for group, profile, kind in [
            ("N1", "steady", None),
            ("N2", "increase", None),
            ("F1", "steady", "thermal"),
            ("F2", "steady", "process"),
            ("F3", "degraded", None),
            ("F4", "mismatch", None),
        ]:
            name = f"e2-trial-{len(rows):04d}"
            data = output / "datasets" / name
            generate_case(root, data, name, seed, profile=profile, kind=kind, e2=True)
            predictions = output / "predictions" / name
            infer_e2_case(data, predictions, model, model_dir, config, reference)
            if (
                fingerprint({"configuration": config.model_dump(mode="json"), "model": model})
                != frozen
            ):
                raise RuntimeError("Model changed during evaluation")
            rows.append({"case_id": name, **evaluate_e2(data, predictions, group)})
            print("E2", name, flush=True)
    summary = summarize_e2(rows)
    report = {
        "experiment_id": "E2",
        "configuration": benchmark,
        "frozen_model_sha256": frozen,
        "training_datasets": model["training_datasets"],
        "trial_count": len(rows),
        "rows": rows,
        "metrics": summary,
        "runtime_s": time.perf_counter() - started,
        "process_peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        "software_version": __import__("twinguard").__version__,
        "git_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip(),
        "label_definition": "Process >1000 Pa or local surface/thermal >1 degC; quality-only and out-of-range groups reported separately; no hazard thresholds",
    }
    save_json(output / "report.json", report)
    save_json(output / "benchmark.json", benchmark)
    return report


def summarize_e2(rows):
    summary = {}
    for group in ["N1", "N2", "F1", "F2", "F3", "F4"]:
        selected = [row for row in rows if row["group"] == group]
        summary[group] = {
            "trials": len(selected),
            "operating": {
                method: {
                    "mean_false_positive_rate": float(
                        np.mean(
                            [
                                r["operating"][method]["false_positive_rate"]
                                for r in selected
                                if r["operating"][method]["false_positive_rate"] is not None
                            ]
                        )
                    ),
                    "mean_recall": float(
                        np.mean(
                            [
                                r["operating"][method]["recall"]
                                for r in selected
                                if r["operating"][method]["recall"] is not None
                            ]
                        )
                    )
                    if any(r["operating"][method]["recall"] is not None for r in selected)
                    else None,
                    "mean_inconclusive_fraction": float(
                        np.mean([r["operating"][method]["inconclusive_fraction"] for r in selected])
                    ),
                    "first_detection_delays_s": [
                        r["operating"][method]["first_detection_delay_s"] for r in selected
                    ],
                }
                for method in ["static", "conditioned", "conditioned_quality"]
            },
            "thermal": {
                method: thermal_summary(
                    [t for r in selected for t in r["thermal"] if t["method"] == method]
                )
                for method in ["static", "conditioned"]
            },
        }
    return summary
