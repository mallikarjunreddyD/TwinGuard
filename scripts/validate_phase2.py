"""Generate measured virtual-sensor diagnostics and actual observation visualizations."""

import argparse
import json
from pathlib import Path
import resource
import time
import numpy as np
from twinguard.core.contracts import InspectionCapture
from twinguard.core.observations import load_public_observations, load_capture_arrays
from twinguard.plant.io import simulator_from_scenario
from twinguard.sensing.acquisition import acquire, load_installation
from twinguard.sensing.visualize import visualize_run
from twinguard.sensing.export import write_manifest
from twinguard.evaluation.sensing import validate_sensing_run, attach_plant_truth


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir", type=Path, default=Path("datasets/synthetic/generated/phase2-validation")
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output_dir
    if output.exists() and any(output.iterdir()):
        parser.error("Choose an empty validation directory")
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    reports = {}
    simulators = {}
    for name in ("S0", "S1", "S2", "S3", "S4", "S5"):
        simulator = simulator_from_scenario(root / f"scenarios/{name}.yaml", root)
        simulators[name] = simulator
        config = load_installation(root / "configs/sensing/L1.yaml")
        acquire(simulator.sensing_reader(), simulator.scenario, config, output / name)
        attach_plant_truth(output / name, simulator)
        reports[name + "-L1"] = validate_sensing_run(output / name)
        print("Acquired", name, flush=True)
    for level in ("L0", "moderate", "L2"):
        name = "S2-" + level
        config = load_installation(root / f"configs/sensing/{level}.yaml")
        simulator = simulators["S2"]
        acquire(simulator.sensing_reader(), simulator.scenario, config, output / name)
        attach_plant_truth(output / name, simulator)
        reports[name] = validate_sensing_run(output / name)
        print("Acquired", name, flush=True)
    # Repeat independently with reverse modality order. No observation is copied.
    simulator = simulators["S2"]
    config = load_installation(root / "configs/sensing/L1.yaml")
    acquire(
        simulator.sensing_reader(),
        simulator.scenario,
        config,
        output / "S2-repeat",
        execution_order=["thermal", "lidar"],
    )

    attach_plant_truth(output / "S2-repeat", simulator)

    def ordered(path):
        return sorted(
            load_public_observations(path),
            key=lambda r: (
                getattr(r, "capture_id", getattr(r, "observation_id", "")),
                r.received_at,
                r.delivery_status,
            ),
        )

    first, second = ordered(output / "S2"), ordered(output / "S2-repeat")
    metadata_equal = first == second
    arrays_equal = True
    for a, b in zip(first, second):
        if isinstance(a, InspectionCapture):
            left, right = (
                load_capture_arrays(output / "S2", a),
                load_capture_arrays(output / "S2-repeat", b),
            )
            arrays_equal &= all(
                np.array_equal(left[key], right[key], equal_nan=True) for key in left
            )
    for name in ("S1", "S2", "S3", "S2-L2"):
        path = output / name
        visualize_run(path)
        manifest = json.loads((path / "manifest.json").read_text())
        records = load_public_observations(path)
        config = load_installation(path / "evaluation_private/installation.json")
        write_manifest(
            path,
            manifest["acquisition_namespace"],
            manifest["master_seed"],
            config,
            [r for r in records if isinstance(r, InspectionCapture)],
            True,
        )
        print("Rendered", name, flush=True)
    import open3d

    report = {
        "label": "Virtual sensor-model validation against separately stored modeled references; not physical accuracy or fault detection",
        "backend": "Open3D CPU RaycastingScene " + open3d.__version__,
        "runs": reports,
        "reproducibility": {
            "metadata_equal": bool(metadata_equal),
            "numeric_arrays_equal": bool(arrays_equal),
            "reverse_modality_order": True,
        },
        "total_runtime_s": time.perf_counter() - started,
        "process_peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        "resource_scope": "Linux process peak including Open3D import, physical plant, ten acquisitions and plotting",
    }
    (output / "sensing_validation.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n"
    )
    print(
        json.dumps(
            {
                "reproducibility": report["reproducibility"],
                "runtime_s": report["total_runtime_s"],
                "peak_rss_mib": report["process_peak_rss_mib"],
            },
            indent=2,
        )
    )
    return 0 if metadata_equal and arrays_equal else 1


if __name__ == "__main__":
    raise SystemExit(main())
