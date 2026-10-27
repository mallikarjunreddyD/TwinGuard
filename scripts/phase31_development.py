from pathlib import Path
import json
import time
from twinguard.analytics.config import AnalyticsConfig
from twinguard.analytics.reference import load_reference
from twinguard.analytics.pipeline import analyze_geometry, save_json, fingerprint
from twinguard.evaluation.geometric_studies import capture_paths
from twinguard.evaluation.analytics import evaluate_e1, summarize_e1

root = Path.cwd()
run = root / "experiments/outputs/phase3_1"
data = run / "development-data"
config = AnalyticsConfig()
reference = load_reference(root / "configs/analytics/accepted_reference.json")
cal = json.loads((run / "b31_calibration_v1.json").read_text())
oldcal = json.loads((run / "baseline-reproduction/geometry_calibration.json").read_text())
rows = []
start = time.perf_counter()
for trial in [
    r for r in json.loads((data / "index.json").read_text()) if r["partition"] == "development"
]:
    output = run / "development-predictions-v1" / trial["case_id"]
    analyze_geometry(
        *capture_paths(data / trial["case_id"]),
        config,
        reference,
        output,
        oldcal,
        methods=["B3", "B3.1"],
        improved_calibration=cal,
    )
    rows.extend(evaluate_e1(data / trial["case_id"], output, trial))
    if len(rows) % 40 == 0:
        print("development", len(rows) // 2, flush=True)
save_json(
    run / "development_report_v1.json",
    {
        "rows": rows,
        "metrics": summarize_e1(rows),
        "configuration_sha256": fingerprint(config),
        "calibration_sha256": fingerprint(cal),
        "runtime_s": time.perf_counter() - start,
    },
)
print("Finished development", flush=True)
