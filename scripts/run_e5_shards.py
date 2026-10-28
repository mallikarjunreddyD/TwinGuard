"""Bounded independent trial processes; identical frozen planner/configuration per shard."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import json
import os
import yaml
from twinguard.evaluation.inspection_experiments import run_e5, SCENARIOS, report_figures

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "experiments/outputs/phase6-E5-recovered"


def execute(task):
    index, output = task
    settings = yaml.safe_load((ROOT / "configs/experiments/E5.yaml").read_text())
    settings["scenario_ids"] = list(SCENARIOS)[index::4]
    return run_e5(ROOT, Path(output) / f"shard-{index}", settings)


if __name__ == "__main__":
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "experiments/outputs/E5-new-run")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    args = parser.parse_args()
    OUTPUT = args.output.resolve()
    OUTPUT.mkdir(parents=True, exist_ok=False)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        reports = list(pool.map(execute, [(index, str(OUTPUT)) for index in range(4)]))
    rows = []
    for index in range(4):
        rows += json.loads((OUTPUT / f"shard-{index}/trial_table.json").read_text())
    (OUTPUT / "trial_table.json").write_text(json.dumps(rows, indent=2) + "\n")
    report = {
        "experiment_id": "E5",
        "status": "executed",
        "independent_seeds": 30,
        "scenario_classes": 18,
        "trial_count": len(rows) // 4,
        "method_runs": len(rows),
        "shards": reports,
        "scope": "Four independent CPU trial processes, unchanged planner weights/sensor models, paired seeds within each trial",
    }
    (OUTPUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    report_figures(OUTPUT)
