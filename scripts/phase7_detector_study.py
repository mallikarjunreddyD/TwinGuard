from pathlib import Path
import argparse
from twinguard.evaluation.phase7_research import detector_campaign

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--partition", choices=("development", "heldout"), default="development")
    p.add_argument("--workers", type=int, choices=(1, 2), default=2)
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--resume", action="store_true")
    args = p.parse_args()
    print(
        detector_campaign(
            Path(__file__).resolve().parents[1],
            args.output,
            args.partition,
            args.workers,
            args.smoke,
            args.resume,
        )
    )
