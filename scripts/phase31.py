"""Reproduce a single Phase 3.1 stage; use new/empty generated output directories."""

import argparse
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "stage",
        choices=[
            "baseline",
            "diagnose",
            "development-data",
            "calibrate",
            "develop",
            "heldout",
            "figures",
        ],
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]

    def run(script):
        subprocess.run([sys.executable, str(root / "scripts" / script)], cwd=root, check=True)

    if args.stage == "baseline":
        subprocess.run(
            [
                sys.executable,
                "-m",
                "twinguard.cli",
                "experiment",
                "run",
                "E1",
                "--config",
                "experiments/E1.yaml",
                "--output-dir",
                "experiments/outputs/phase3_1/baseline-reproduction",
            ],
            cwd=root,
            check=True,
        )
        run("phase31_baseline_evidence.py")
    elif args.stage == "diagnose":
        from twinguard.evaluation.geometric_studies import diagnostics
        from twinguard.evaluation.geometric_diagnostics_report import build_root_report

        diagnostics(
            root,
            root / "experiments/outputs/phase3_1/diagnostics",
            root / "experiments/outputs/phase3_1/baseline-reproduction",
        )
        run("phase31_trace_baseline.py")
        build_root_report(root)
    elif args.stage == "development-data":
        run("phase31_generate_development.py")
    elif args.stage == "calibrate":
        run("phase31_calibrate.py")
    elif args.stage == "develop":
        run("phase31_development.py")
    elif args.stage == "heldout":
        run("phase31_heldout.py")
    else:
        from twinguard.evaluation.geometric_figures import figures

        print(figures(root, heldout=True))


if __name__ == "__main__":
    main()
