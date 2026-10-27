from pathlib import Path
import json
from .config import load_plant_config
from .model import create_baseline_plant
from .io import (
    simulator_from_scenario,
    export_run,
    load_run,
    export_snapshot,
    time_name,
    refresh_checksums,
    write_json,
)


def add_commands(sub):
    plant = sub.add_parser("plant")
    actions = plant.add_subparsers(dest="plant_command", required=True)
    build = actions.add_parser("build")
    build.add_argument("--config", type=Path, default=Path("configs/plant.yaml"))
    build.add_argument("--output-dir", type=Path, required=True)
    build.add_argument("--seed", type=int, default=0)
    simulate = actions.add_parser("simulate")
    simulate.add_argument("--scenario", type=Path, required=True)
    simulate.add_argument("--config", type=Path)
    simulate.add_argument("--output-dir", type=Path, required=True)
    for name in ("snapshot", "visualize"):
        command = actions.add_parser(name)
        command.add_argument("--run-dir", type=Path, required=True)
        command.add_argument("--time", type=float, required=True)
        if name == "snapshot":
            command.add_argument("--format", choices=["glb", "ply"], default="glb")
    inspect = actions.add_parser("inspect")
    inspect.add_argument("--run-dir", type=Path, required=True)


def execute(args):
    if args.plant_command == "build":
        config = load_plant_config(args.config)
        baseline = create_baseline_plant(config, args.seed)
        output = args.output_dir
        if output.exists() and any(output.iterdir()):
            raise ValueError("Output directory must be empty")
        output.mkdir(parents=True, exist_ok=True)
        (output / "plant.glb").write_bytes(baseline.scene().export(file_type="glb"))
        for aid in baseline.asset_registry:
            mesh = baseline.mesh(aid)
            mesh.apply_transform(baseline.world_pose(aid).matrix)
            mesh.export(output / f"{aid}.ply")
        write_json(
            output / "assets.json",
            [
                a.model_copy(
                    update={"geometry": a.geometry.model_copy(update={"uri": f"{a.asset_id}.ply"})}
                ).model_dump(mode="json")
                for a in baseline.asset_registry.values()
            ],
        )
        write_json(output / "plant_config.json", config)
        print(output)
    elif args.plant_command == "simulate":
        simulator = simulator_from_scenario(args.scenario, args.root, args.config)
        manifest = export_run(simulator, args.output_dir)
        print(f"Generated {manifest['scenario_id']} in {args.output_dir}")
    elif args.plant_command == "inspect":
        print(json.dumps(json.loads((args.run_dir / "manifest.json").read_text()), indent=2))
    else:
        simulator = load_run(args.run_dir)
        snapshot = simulator.state_at(args.time)
        if args.plant_command == "snapshot":
            output = export_snapshot(
                snapshot, args.run_dir / "snapshots" / time_name(args.time), (args.format,)
            )
        else:
            from .visualize import render

            output = render(
                snapshot,
                args.run_dir / "visualization" / f"{time_name(args.time)}.png",
                simulator.baseline,
            )
        if args.plant_command == "snapshot":
            path = args.run_dir / "manifest.json"
            manifest = json.loads(path.read_text())
            manifest["snapshot_times_s"] = sorted(set(manifest["snapshot_times_s"] + [args.time]))
            write_json(path, manifest)
            truth_path = args.run_dir / "restricted/ground_truth.json"
            truth = json.loads(truth_path.read_text())
            truth = [record for record in truth if record["time_s"] != args.time]
            truth.append(
                simulator.ground_truth_at(args.time, manifest["run_id"]).model_dump(mode="json")
            )
            write_json(truth_path, sorted(truth, key=lambda record: record["time_s"]), private=True)
        refresh_checksums(args.run_dir)
        print(output)
