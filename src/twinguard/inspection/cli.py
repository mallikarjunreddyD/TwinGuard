"""Reproducible public-input inspection CLI."""

from pathlib import Path
import json
from .observations import load_config, load_snapshot
from .contracts import InspectionPlanningRequest, InspectionPlan


def add_commands(sub):
    parser = sub.add_parser("inspection")
    actions = parser.add_subparsers(dest="inspection_command", required=True)
    for name in ("validate-config", "coverage", "candidates", "plan", "replan"):
        p = actions.add_parser(name)
        p.add_argument("--config", type=Path, default=Path("configs/inspection/planner.yaml"))
        if name != "validate-config":
            p.add_argument("--snapshot", type=Path, required=True)
            p.add_argument("--output-dir", type=Path, required=True)
        if name in ("plan", "replan"):
            p.add_argument("--method", choices=["P0", "P1", "P2", "P3"], default="P3")
            p.add_argument("--budget-views", type=int, default=4)
            p.add_argument("--budget-s", type=float, default=120)
        if name == "replan":
            p.add_argument("--previous-plan", type=Path, required=True)


def execute(args):
    config = load_config(args.config)
    if args.inspection_command == "validate-config":
        print("Valid", config.configuration_id)
        return
    from .coverage import ReferenceSurface, qualified_history
    from .candidates import generate
    from .optimizer import plan

    snapshot = load_snapshot(args.snapshot)
    surface = ReferenceSurface(
        args.root / config.reference_path, config.reference_sha256, config.cell_m
    )
    output = args.output_dir
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output must be empty")
    output.mkdir(parents=True, exist_ok=True)
    if args.inspection_command == "coverage":
        result = {
            "qualified_cells": sorted(qualified_history(surface, snapshot, config)),
            "coverage": [v.model_dump(mode="json") for v in snapshot.coverage],
        }
    else:
        candidates = generate(surface, snapshot, config, args.root)
        if args.inspection_command == "candidates":
            result = [c.model_dump(mode="json") for c in candidates]
        else:
            if args.inspection_command == "replan":
                from .replanning import recommend

                previous = InspectionPlan.model_validate_json(args.previous_plan.read_text())
                recommend(previous, snapshot)
            request = InspectionPlanningRequest(
                request_id=output.name,
                method=args.method,
                budget_views=args.budget_views,
                budget_s=args.budget_s,
            )
            result = plan(surface, snapshot, config, request, candidates).model_dump(mode="json")
    (output / (args.inspection_command + ".json")).write_text(json.dumps(result, indent=2) + "\n")
    print(output)
