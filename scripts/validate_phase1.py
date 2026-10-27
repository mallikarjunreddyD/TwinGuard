"""Generate measured Phase 1 validation artifacts; no algorithm performance metrics."""

from datetime import timedelta
import argparse
import json
from pathlib import Path
import resource
import time
import numpy as np
from twinguard.plant.io import simulator_from_scenario, export_run, refresh_checksums, write_json
from twinguard.plant.simulator import PlantSimulator
from twinguard.plant.config import load_plant_config
from twinguard.plant.model import create_baseline_plant
from twinguard.plant.visualize import render
from twinguard.evaluation.contracts import FaultInjection


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir", type=Path, default=Path("datasets/synthetic/generated/phase1-validation")
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output_dir
    if output.exists() and any(output.iterdir()):
        parser.error("Choose a new, empty output directory")
    output.mkdir(parents=True, exist_ok=True)
    total_start = time.perf_counter()
    report = {
        "label": "SIMULATION GROUND TRUTH: numerical implementation validation, not sensing accuracy",
        "geometry": [],
        "runs": {},
        "deformation": [],
    }
    baseline = create_baseline_plant(load_plant_config(root / "configs/plant.yaml"), 42)
    for aid in baseline.asset_registry:
        mesh = baseline.mesh(aid)
        world = mesh.copy()
        world.apply_transform(baseline.world_pose(aid).matrix)
        report["geometry"].append(
            {
                "asset_id": aid,
                "vertices": len(mesh.vertices),
                "faces": len(mesh.faces),
                "world_bounds_m": world.bounds.tolist(),
                "watertight": bool(mesh.is_watertight),
                "min_triangle_area_m2": float(mesh.area_faces.min()),
            }
        )
    sims = {}
    for name in ("S0", "S1", "S2", "S3", "S4", "S5"):
        start = time.perf_counter()
        sim = simulator_from_scenario(root / f"scenarios/{name}.yaml", root)
        manifest = export_run(sim, output / name)
        sims[name] = sim
        report["runs"][name] = {
            "total_generation_runtime_s": time.perf_counter() - start,
            "export_runtime_s": manifest["generation_runtime_s"],
            "time_grid_samples": len(sim.time_grid()),
            "snapshot_times_s": manifest["snapshot_times_s"],
        }
    for amplitude in (0.01, 0.02, 0.03, 0.05):
        fault = (
            sims["S2"]
            ._faults[0]
            .model_copy(
                update={
                    "true_displacement_m": amplitude,
                    "severity_parameters": {"amplitude_m": amplitude},
                }
            )
        )
        sim = PlantSimulator(baseline, sims["S2"].scenario, [fault])
        original = baseline.mesh("BW-01").vertices
        current = sim.state_at(60).assets["BW-01"].vertices_local_m
        actual = float(np.linalg.norm(current - original, axis=1).max())
        report["deformation"].append(
            {
                "configured_m": amplitude,
                "measured_mesh_peak_m": actual,
                "absolute_error_m": abs(actual - amplitude),
                "tolerance_m": 1e-10,
                "pass": abs(actual - amplitude) <= 1e-10,
            }
        )
    state = sims["S1"].state_at(60)
    wall = state.assets["BW-01"]
    delta = state.operating.process_temperature_c - baseline.config.dynamics.reference_temperature_c
    expected = 12e-6 * 2.4 * delta
    measured = float(np.ptp(wall.vertices_local_m[:, 2]) - 2.4)
    report["thermal_expansion"] = {
        "time_s": 60,
        "temperature_change_c": delta,
        "analytical_m": expected,
        "measured_extent_change_m": measured,
        "absolute_error_m": abs(expected - measured),
        "tolerance_m": 1e-12,
        "pass": abs(expected - measured) <= 1e-12,
    }
    support_fault = FaultInjection(
        fault_id="support-demo",
        asset_id="SUP-01",
        category="structural_support_displacement",
        start_at=sims["S0"].scenario.simulation_start,
        end_at=sims["S0"].scenario.simulation_start + timedelta(seconds=90),
        severity_parameters={},
        affected_region_id="surface",
        displacement_vector_m=(0.02, -0.01, 0.005),
        persistence="persistent",
        ground_truth_artifacts=[],
    )
    scenario = sims["S0"].scenario.model_copy(
        update={
            "scenario_id": "SUPPORT",
            "fault_config_references": ["support-demo"],
            "description": "Illustrative controlled support translation, not a calibrated engineering failure",
        }
    )
    support = PlantSimulator(baseline, scenario, [support_fault])
    export_run(support, output / "SUPPORT")
    actual = (
        support.state_at(60).assets["SUP-01"].vertices_world_m
        - sims["S0"].state_at(60).assets["SUP-01"].vertices_world_m
    )
    error = float(np.max(np.abs(actual - np.array([0.02, -0.01, 0.005]))))
    report["support_translation"] = {
        "configured_m": [0.02, -0.01, 0.005],
        "measured_mean_m": actual.mean(axis=0).tolist(),
        "max_absolute_error_m": error,
        "tolerance_m": 1e-12,
        "pass": error < 1e-12,
    }
    first = sims["S2"].state_at(60)
    replay = simulator_from_scenario(root / "scenarios/S2.yaml", root)
    replay.state_at(120)
    replay.state_at(0)
    second = replay.state_at(60)
    report["reproducibility"] = {
        "bitwise_mesh_equal": all(
            np.array_equal(first.assets[k].vertices_world_m, second.assets[k].vertices_world_m)
            for k in first.assets
        ),
        "operating_state_equal": first.operating == second.operating,
    }
    for name, sim in [
        ("S0", sims["S0"]),
        ("S2", sims["S2"]),
        ("S3", sims["S3"]),
        ("SUPPORT", support),
    ]:
        render(sim.state_at(60), output / name / "visualization" / "t_60.png", sim.baseline)
        refresh_checksums(output / name)
    # Combined actual state: 30 mm wall bulge + support shift + 12 degC hotspot.
    combined = PlantSimulator(
        baseline, sims["S2"].scenario, [sims["S2"]._faults[0], support_fault, sims["S3"]._faults[0]]
    )
    render(combined.state_at(60), output / "combined_ground_truth.png", baseline)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(3, 1, figsize=(9, 8), sharex=True, layout="constrained")
    for name in ("S0", "S1", "S4"):
        rows = json.loads((output / name / "operating_states.json").read_text())
        x = [r["time_s"] for r in rows]
        for axis, key in zip(
            axes, ["normalized_load", "process_temperature_c", "process_pressure_pa"]
        ):
            axis.plot(x, [r[key] for r in rows], label=name)
            axis.set_ylabel(key)
            axis.grid(alpha=0.2)
            axis.legend()
    axes[-1].set_xlabel("Simulated time (s)")
    fig.suptitle("Simulated process state: common load-driven dynamics and explicit disturbance")
    fig.savefig(output / "operating_traces.png", dpi=130)
    plt.close(fig)
    report["total_runtime_s"] = time.perf_counter() - total_start
    report["process_peak_rss_mib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    report["memory_scope"] = (
        "Linux process peak RSS, includes exports and Matplotlib rendering; not an isolated simulator memory benchmark"
    )
    report["all_numerical_checks_pass"] = (
        all(r["pass"] for r in report["deformation"])
        and report["thermal_expansion"]["pass"]
        and report["support_translation"]["pass"]
        and all(report["reproducibility"].values())
    )
    write_json(output / "validation.json", report)
    print(json.dumps(report, indent=2))
    return 0 if report["all_numerical_checks_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
