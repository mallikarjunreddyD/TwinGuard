from pathlib import Path
import json
import time
from twinguard.analytics.config import AnalyticsConfig
from twinguard.analytics.clouds import load_scan
from twinguard.analytics.reference import load_reference
from twinguard.analytics.registration import register
from twinguard.analytics.geometric_improved import calibrate
from twinguard.analytics.pipeline import save_json
from twinguard.evaluation.geometric_studies import capture_paths

root = Path.cwd()
out = root / "experiments/outputs/phase3_1"
data = out / "development-data"
rows = json.loads((data / "index.json").read_text())
config = AnalyticsConfig()
reference = load_reference(root / "configs/analytics/accepted_reference.json")
ids = []


def samples():
    for i, row in enumerate(r for r in rows if r["partition"] == "healthy-calibration"):
        b, c = [load_scan(p, config) for p in capture_paths(data / row["case_id"])]
        reg, points = register(b, c, config, reference, "point_to_point")
        ids.append(b.record.provenance_id)
        if i % 20 == 0:
            print("healthy calibration", i, flush=True)
        yield b, points, reg, row["seed"] < 2215


start = time.perf_counter()
model = calibrate(samples(), config, reference, ids)
model["runtime_s"] = time.perf_counter() - start
save_json(out / "b31_calibration_v1.json", model)
print("multipliers", model["multipliers"], flush=True)
