from pathlib import Path
from datetime import datetime
import json
import time
from .policies import load_policy, policy_hash
from .models import FusionState, OperatorAction
from .io import prepare, save_evidence, read_evidence, write_run
from .engine import replay


def add_commands(sub):
    root = sub.add_parser("fusion")
    commands = root.add_subparsers(dest="fusion_command", required=True)
    for name in ["validate-policy", "prepare", "assess", "replay"]:
        p = commands.add_parser(name)
        p.add_argument("--policy", type=Path, default=Path("configs/fusion/hazards.yaml"))
        if name == "prepare":
            p.add_argument("--analytics-run", type=Path, required=True)
            p.add_argument(
                "--dataset",
                type=Path,
                help="Original public dataset for standalone thermal outputs with capture-only upstream linkage",
            )
            p.add_argument(
                "--clock-quality",
                choices=["unknown", "uncertain", "synchronized"],
                default="unknown",
            )
        if name in ["assess", "replay"]:
            p.add_argument("--evidence", type=Path, required=True)
            p.add_argument("--actions", type=Path)
            p.add_argument("--checkpoint", type=Path)
            p.add_argument("--method", choices=["F0", "F1"], default="F1")
            p.add_argument("--mode", choices=["online", "retrospective"], default="online")
            p.add_argument("--at", type=datetime.fromisoformat, required=name == "assess")
        if name != "validate-policy":
            p.add_argument("--output-dir", type=Path, required=True)


def execute(args):
    policy = load_policy(args.policy)
    if args.fusion_command == "validate-policy":
        print("Valid policy", policy.policy_id, policy.version, policy_hash(policy))
        return
    if args.fusion_command == "prepare":
        values = prepare(args.analytics_run, policy, args.clock_quality, args.dataset)
        save_evidence(
            args.output_dir,
            values,
            {"analytics_run": str(args.analytics_run), "clock_quality": args.clock_quality},
        )
    else:
        values = read_evidence(args.evidence)
        actions = (
            [OperatorAction.model_validate(a) for a in json.loads(args.actions.read_text())]
            if args.actions
            else []
        )
        checkpoint = (
            FusionState.model_validate_json(args.checkpoint.read_text())
            if args.checkpoint
            else None
        )
        started = time.perf_counter()
        state, history = replay(
            values, policy, args.at, actions, checkpoint, args.method, args.mode
        )
        write_run(
            args.output_dir,
            state,
            history,
            policy,
            {
                "processing_runtime_s": time.perf_counter() - started,
                "mode": args.mode,
                "method": args.method,
                "input_manifest": str(args.evidence / "manifest.json"),
            },
        )
    print(args.output_dir)
