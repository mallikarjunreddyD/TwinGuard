from pathlib import Path
import json


def add_commands(sub):
    root = sub.add_parser(
        "analytics", help="Qualified registration, geometry, thermal and operating residuals"
    )
    commands = root.add_subparsers(dest="analytics_command", required=True)
    for name in ["register", "geometry"]:
        p = commands.add_parser(name)
        p.add_argument("--baseline", type=Path, required=True)
        p.add_argument("--current", type=Path, required=True)
        p.add_argument("--config", type=Path, default=Path("configs/analytics/default.yaml"))
        p.add_argument(
            "--reference", type=Path, default=Path("configs/analytics/accepted_reference.json")
        )
        p.add_argument("--calibration", type=Path)
        p.add_argument("--improved-calibration", type=Path)
        p.add_argument("--methods", nargs="+", choices=["B1", "B2", "B3", "B3.1"])
        p.add_argument("--output-dir", type=Path, required=True)
        if name == "register":
            p.add_argument(
                "--method",
                choices=["point_to_point", "robust_point_to_plane"],
                default="robust_point_to_plane",
            )
    for name in ["calibrate-operating", "calibrate-thermal", "operating", "thermal"]:
        p = commands.add_parser(name)
        p.add_argument("--output-dir", type=Path, required=True)
        p.add_argument("--config", type=Path, default=Path("configs/analytics/default.yaml"))
        if name.startswith("calibrate"):
            p.add_argument("--dataset", type=Path, nargs="+", required=True)
        if name == "calibrate-thermal":
            p.add_argument("--operating-model", type=Path, required=True)
        if name == "operating":
            p.add_argument("--dataset", type=Path, required=True)
            p.add_argument("--model", type=Path, required=True)
            p.add_argument(
                "--method",
                choices=["static", "conditioned", "conditioned_quality"],
                default="conditioned_quality",
            )
        if name == "thermal":
            p.add_argument("--capture", type=Path, required=True)
            p.add_argument("--reference", type=Path, required=True)
            p.add_argument("--method", choices=["static", "conditioned"], default="conditioned")


def execute(args):
    from .config import load_config
    from .pipeline import analyze_geometry, save_json, seal_predictions
    from .reference import load_reference

    config = load_config(args.config)
    if args.analytics_command in ("register", "geometry"):
        reference = load_reference(args.reference)
        calibration = json.loads(args.calibration.read_text()) if args.calibration else None
        methods = (
            args.methods
            if args.analytics_command == "geometry"
            else ["B2" if args.method == "point_to_point" else "B3"]
        )
        analyze_geometry(
            args.baseline,
            args.current,
            config,
            reference,
            args.output_dir,
            calibration,
            methods,
            json.loads(args.improved_calibration.read_text())
            if args.improved_calibration
            else None,
        )
    elif args.analytics_command == "calibrate-operating":
        from .operating import calibrate_operating

        if args.output_dir.exists() and any(args.output_dir.iterdir()):
            raise ValueError("Model output must be empty")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        save_json(
            args.output_dir / "operating_model.json", calibrate_operating(args.dataset, config)
        )
    elif args.analytics_command == "calibrate-thermal":
        from .thermal import calibrate_thermal

        calibrate_thermal(
            args.dataset, json.loads(args.operating_model.read_text()), config, args.output_dir
        )
    elif args.analytics_command == "operating":
        from .operating import infer_operating, measured_records

        if args.output_dir.exists() and any(args.output_dir.iterdir()):
            raise ValueError("Prediction output must be empty")
        model = json.loads(args.model.read_text())
        results = infer_operating(measured_records(args.dataset), model, config, args.method)
        save_json(args.output_dir / "operating.json", [r.model_dump(mode="json") for r in results])
        seal_predictions(
            args.output_dir, config, {"dataset": str(args.dataset), "model": model["model_id"]}
        )
    else:
        from .thermal import infer_thermal
        from twinguard.core.observations import load_public_observations
        from twinguard.core.contracts import InspectionCapture
        import numpy as np

        if args.output_dir.exists() and any(args.output_dir.iterdir()):
            raise ValueError("Prediction output must be empty")
        root = next((p for p in args.capture.parents if (p / "manifest.json").exists()), None)
        if root is None:
            raise ValueError("Thermal capture requires public observation manifest")
        record = next(
            (
                r
                for r in load_public_observations(root)
                if isinstance(r, InspectionCapture) and r.capture_id == args.capture.stem
            ),
            None,
        )
        if record is None:
            raise ValueError("Unknown thermal capture")
        model_dir = args.reference.parent if args.reference.is_file() else args.reference
        result, arrays = infer_thermal(root, record, model_dir, config, method=args.method)
        save_json(args.output_dir / "thermal.json", result)
        np.savez_compressed(args.output_dir / "thermal_residuals.npz", **arrays)
        seal_predictions(
            args.output_dir, config, {"capture": record.capture_id, "model": str(model_dir)}
        )
    print(args.output_dir)
