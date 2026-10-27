from pathlib import Path
from twinguard.evaluation.geometric_studies import generate
from twinguard.analytics.pipeline import save_json

root = Path.cwd()
out = root / "experiments/outputs/phase3_1/development-data"
out.mkdir(exist_ok=False)
rows = []
for partition, seeds, amplitudes in [
    ("healthy-calibration", range(2200, 2230), [0]),
    ("development", range(2100, 2110), [0, 0.01, 0.02, 0.03, 0.05]),
]:
    for seed in seeds:
        for level in ["L0", "L1", "L2"]:
            for amplitude in amplitudes:
                for view in ["same", "changed"]:
                    case = f"dev-{len(rows):04d}"
                    generate(root, out / case, case, seed, level, amplitude, view)
                    rows.append(
                        {
                            "case_id": case,
                            "partition": partition,
                            "seed": seed,
                            "fidelity": level,
                            "amplitude_m": amplitude,
                            "viewpoint": view,
                        }
                    )
                    if len(rows) % 30 == 0:
                        print("generated development", len(rows), flush=True)
save_json(out / "index.json", rows)
