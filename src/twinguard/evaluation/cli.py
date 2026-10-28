from pathlib import Path
import json
import yaml
import subprocess
import sys


def add_commands(sub):
    root = sub.add_parser("experiment")
    commands = root.add_subparsers(dest="experiment_command", required=True)
    run = commands.add_parser("run")
    run.add_argument("experiment_id", choices=["E1", "E2", "E3", "E4"])
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--output-dir", type=Path)
    run.add_argument("--smoke", action="store_true")
    run.add_argument("--project", default="twinguard-e4")
    report = commands.add_parser("report")
    report.add_argument("--run-dir", type=Path, required=True)


def execute(args):
    if args.experiment_command == "report":
        report = json.loads((args.run_dir / "report.json").read_text())
        if report.get("experiment") == "E4":
            subprocess.run(
                [
                    sys.executable,
                    str(args.root / "scripts/summarize_e4.py"),
                    "--run-dir",
                    str(args.run_dir.resolve()),
                ],
                cwd=args.root,
                check=True,
            )
            return
        if json.loads((args.run_dir / "report.json").read_text()).get("experiment_id") == "E3":
            from .fusion_report import report_figures

            print(report_figures(args.run_dir))
            return
        from .visualize import experiment_figures

        print(experiment_figures(args.run_dir))
        return
    if args.experiment_id == "E4":
        config = yaml.safe_load(args.config.read_text())
        if config.get("experiment_id") != "E4":
            raise ValueError("Experiment/configuration mismatch")
        command = [
            sys.executable,
            str(args.root / "scripts/run_e4.py"),
            "--output",
            str((args.output_dir or args.root / "experiments/outputs/E4").resolve()),
            "--project",
            args.project,
        ]
        if args.smoke:
            command.append("--smoke")
        subprocess.run(command, cwd=args.root, check=True)
        return
    from .contracts import ExperimentBenchmark
    from .experiments import run_e1, run_e2

    raw = yaml.safe_load(args.config.read_text())
    if "benchmark_reference" in raw:
        raw = yaml.safe_load((args.root / raw["benchmark_reference"]).read_text())
    if args.experiment_id == "E3":
        from .fusion_experiments import run_e3
        from .contracts import FusionBenchmark

        raw = FusionBenchmark.model_validate(raw).model_dump(mode="json")

        result = run_e3(
            args.root, args.output_dir or args.root / "experiments/outputs/E3", raw, args.smoke
        )
        print(
            json.dumps(
                {
                    "experiment": "E3",
                    "controlled_cases": result["controlled"]["cases"],
                    "end_to_end_cases": result["end_to_end"]["cases"],
                }
            )
        )
        return
    if args.smoke:
        raw = yaml.safe_load(
            (args.root / f"configs/experiments/{args.experiment_id}-smoke.yaml").read_text()
        )
    benchmark = ExperimentBenchmark.model_validate(raw).model_dump(mode="json")
    if benchmark["experiment_id"] != args.experiment_id:
        raise ValueError("Experiment/configuration mismatch")
    output = args.output_dir or args.root / "experiments/outputs" / args.experiment_id
    result = (run_e1 if args.experiment_id == "E1" else run_e2)(args.root, output, benchmark)
    print(
        json.dumps(
            {
                "experiment": args.experiment_id,
                "trials": result["trial_count"],
                "output": str(output),
            },
            indent=2,
        )
    )
