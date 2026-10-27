from pathlib import Path
import json


def add_commands(sub):
    group = sub.add_parser("sensing", help="Virtual sensor acquisition; no analytics")
    commands = group.add_subparsers(dest="sensing_command", required=True)
    for name in ("lidar", "thermal", "iot", "simulate"):
        command = commands.add_parser(name)
        command.add_argument("--scenario", type=Path, required=True)
        command.add_argument("--config", type=Path, default=Path("configs/sensing/L1.yaml"))
        command.add_argument("--output-dir", type=Path, required=True)
        if name in ("lidar", "thermal"):
            command.add_argument("--time", type=float, required=True)
    for name in ("validate", "visualize"):
        command = commands.add_parser(name)
        command.add_argument("--run-dir", type=Path, required=True)


def execute(args):
    if args.sensing_command == "validate":
        from twinguard.evaluation.sensing import validate_sensing_run

        print(json.dumps(validate_sensing_run(args.run_dir), indent=2))
    elif args.sensing_command == "visualize":
        from .visualize import visualize_run

        print(visualize_run(args.run_dir))
        from .export import write_manifest
        from .acquisition import load_installation

        manifest = json.loads((args.run_dir / "manifest.json").read_text())
        from twinguard.core.observations import load_public_observations
        from twinguard.core.contracts import InspectionCapture

        records = load_public_observations(args.run_dir)
        config = load_installation(args.run_dir / "evaluation_private/installation.json")
        write_manifest(
            args.run_dir,
            manifest["acquisition_namespace"],
            manifest["master_seed"],
            config,
            [r for r in records if isinstance(r, InspectionCapture)],
            any(not isinstance(r, InspectionCapture) for r in records),
        )
    else:
        from twinguard.plant.io import simulator_from_scenario
        from .acquisition import load_installation, acquire

        simulator = simulator_from_scenario(args.scenario, args.root)
        config = load_installation(args.config)
        manifest = acquire(
            simulator.sensing_reader(),
            simulator.scenario,
            config,
            args.output_dir,
            "all" if args.sensing_command == "simulate" else args.sensing_command,
            getattr(args, "time", None),
        )
        from twinguard.evaluation.sensing import attach_plant_truth

        attach_plant_truth(args.output_dir, simulator)
        print(f"Generated {len(manifest.observations)} observation sources in {args.output_dir}")
