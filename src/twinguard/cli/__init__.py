import importlib
import argparse
import json
from pathlib import Path
import sys
import yaml
from twinguard import __version__, SCHEMA_VERSION
from twinguard.core.config import load_scenario
from twinguard.core.registry import PUBLIC_MODELS, export_schemas

DIRECTORIES = [
    "configs",
    "scenarios",
    "datasets/synthetic",
    "datasets/public",
    "datasets/hybrid",
    "datasets/ground_truth",
    "experiments",
    "schemas",
    "tests",
    "deployment",
    "docs",
    "scripts",
]


def main(argv=None):
    parser = argparse.ArgumentParser(prog="twinguard")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("doctor", "list-scenarios", "version"):
        sub.add_parser(command)
    validate = sub.add_parser("validate-config")
    validate.add_argument("file", type=Path)
    data = sub.add_parser("validate-data")
    data.add_argument("file", type=Path)
    data.add_argument("--kind", choices=sorted(PUBLIC_MODELS), required=True)
    export = sub.add_parser("export-schemas")
    export.add_argument("--output", type=Path)
    from twinguard.plant.cli import add_commands

    add_commands(sub)
    from twinguard.sensing.cli import add_commands as add_sensing_commands

    add_sensing_commands(sub)
    from twinguard.analytics.cli import add_commands as add_analytics
    from twinguard.evaluation.cli import add_commands as add_experiments

    from twinguard.fusion.cli import add_commands as add_fusion

    from twinguard.inspection.cli import add_commands as add_inspection

    add_inspection(sub)
    add_fusion(sub)
    add_analytics(sub)
    add_experiments(sub)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspection":
            from twinguard.inspection.cli import execute

            execute(args)
        elif args.command == "fusion":
            from twinguard.fusion.cli import execute

            execute(args)
        elif args.command == "analytics":
            from twinguard.analytics.cli import execute

            execute(args)
        elif args.command == "experiment":
            from twinguard.evaluation.cli import execute

            execute(args)
        elif args.command == "sensing":
            from twinguard.sensing.cli import execute

            execute(args)
        elif args.command == "plant":
            from twinguard.plant.cli import execute

            execute(args)
        elif args.command == "doctor":
            for module in ("pydantic", "numpy", "yaml", "fastapi", "uvicorn"):
                importlib.import_module(module)
            missing = [p for p in DIRECTORIES if not (args.root / p).is_dir()]
            if sys.version_info < (3, 11) or missing:
                raise ValueError(f"Python 3.11+ required; missing directories: {missing}")
            print("Environment OK: Python, required imports and repository directories available")
        elif args.command == "version":
            print(f"TwinGuard {__version__}; schema {SCHEMA_VERSION}")
        elif args.command == "list-scenarios":
            for path in sorted((args.root / "scenarios").glob("*.yaml")):
                print(load_scenario(path, args.root).scenario_id, path.name)
        elif args.command == "validate-config":
            print("Valid scenario:", load_scenario(args.file, args.root).scenario_id)
        elif args.command == "validate-data":
            PUBLIC_MODELS[args.kind].model_validate(json.loads(args.file.read_text()))
            print("Valid", args.kind)
        elif args.command == "export-schemas":
            export_schemas(args.output or args.root / "schemas")
            print("Schemas exported")
    except (ValueError, OSError, TypeError, ImportError, yaml.YAMLError) as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        return 1
    return 0
