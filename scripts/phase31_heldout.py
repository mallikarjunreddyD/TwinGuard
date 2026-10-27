"""Run once after development freeze; never tune using these results."""

from pathlib import Path
from datetime import datetime, timezone
import json
import time
import resource
import subprocess
import hashlib
from twinguard.analytics.config import AnalyticsConfig
from twinguard.analytics.reference import load_reference
from twinguard.analytics.pipeline import analyze_geometry, save_json, fingerprint
from twinguard.evaluation.geometric_studies import generate
from twinguard.evaluation.analytics import evaluate_e1
from twinguard.evaluation.geometric_revalidation import enrich, summarize, paired_bootstrap

root = Path.cwd()
run = root / "experiments/outputs/phase3_1"
output = run / "heldout-v1"
if output.exists():
    raise ValueError("Held-out output exists; a new frozen partition is required for a rerun")
freeze = json.loads((root / "docs/phase3_1/improved_freeze.json").read_text())
config = AnalyticsConfig()
reference = load_reference(root / "configs/analytics/accepted_reference.json")
cal = json.loads((run / "b31_calibration_v1.json").read_text())
oldcal = json.loads((run / "baseline-reproduction/geometry_calibration.json").read_text())
assert fingerprint(cal) == freeze["calibration_sha256"]
for name, digest in freeze["source_sha256"].items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
output.mkdir(parents=True)
save_json(output / "freeze.json", freeze)
rows = []
cases = []
for seed in range(4100, 4130):
    for level in ["L0", "L1", "L2"]:
        for amplitude in [0, 0.01, 0.02, 0.03, 0.05]:
            for view in ["same", "changed"]:
                cases.append(
                    {"seed": seed, "fidelity": level, "amplitude_m": amplitude, "viewpoint": view}
                )
for seed in range(4100, 4110):
    for view in ["partial", "high_pose", "low_overlap"]:
        cases.append({"seed": seed, "fidelity": "L2", "amplitude_m": 0.03, "viewpoint": view})
start = time.perf_counter()
started = datetime.now(timezone.utc).isoformat()
for i, trial in enumerate(cases):
    case = f"trial-{i:04d}"
    trial["case_id"] = case
    data = output / "datasets" / case
    paths = generate(
        root,
        data,
        case,
        trial["seed"],
        trial["fidelity"],
        trial["amplitude_m"],
        trial["viewpoint"],
        variation=trial["seed"] - 4099,
    )
    predictions = output / "predictions" / case
    analyze_geometry(
        *paths,
        config,
        reference,
        predictions,
        oldcal,
        methods=["B1", "B2", "B3", "B3.1"],
        improved_calibration=cal,
    )
    rows.extend(enrich(data, predictions, evaluate_e1(data, predictions, trial), trial))
    assert fingerprint(cal) == freeze["calibration_sha256"]
    if (i + 1) % 20 == 0:
        save_json(
            output / "progress.json",
            {"completed": i + 1, "planned": len(cases), "runtime_s": time.perf_counter() - start},
        )
        print("heldout", i + 1, "/", len(cases), flush=True)
report = {
    "experiment_id": "E1-Phase3.1",
    "trials": len(cases),
    "principal_trials": 900,
    "stress_trials": 30,
    "seeds": list(range(4100, 4130)),
    "started_at": started,
    "ended_at": datetime.now(timezone.utc).isoformat(),
    "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "software_version": __import__("twinguard").__version__,
    "freeze": freeze,
    "rows": rows,
    "metrics": summarize(rows),
    "paired_comparison": paired_bootstrap(rows),
    "runtime_s": time.perf_counter() - start,
    "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
    "statistical_note": "30 independent seeds per amplitude/noise cell, each observed at two paired viewpoints; stress trials reuse ten seeds; engineering scores are not 95% intervals",
}
save_json(output / "report.json", report)
save_json(root / "docs/phase3_1/heldout_results.json", report)
print("HELDOUT COMPLETED", flush=True)
