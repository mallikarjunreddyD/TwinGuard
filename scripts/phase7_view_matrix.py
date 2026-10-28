from pathlib import Path
import argparse
from twinguard.evaluation.viewpoint_campaign import run_diagnostic_matrix

p = argparse.ArgumentParser()
p.add_argument("--output", type=Path, required=True)
p.add_argument("--workers", type=int, choices=(1, 2), default=2)
p.add_argument("--smoke", action="store_true")
args = p.parse_args()
if __name__ == "__main__":
    run_diagnostic_matrix(
        Path(__file__).resolve().parents[1], args.output, args.workers, args.smoke
    )
