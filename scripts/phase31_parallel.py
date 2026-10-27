"""Resume the unchanged frozen benchmark with isolated deterministic CPU workers.

Execution-only optimization: production source, calibration, case IDs/seeds and metrics
are verified against the existing freeze. Existing sealed predictions are never rewritten.
"""

from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import get_context
import json
import time
import resource
import hashlib
import os
import shutil
import subprocess
from twinguard.analytics.config import AnalyticsConfig
from twinguard.analytics.reference import load_reference
from twinguard.analytics.pipeline import analyze_geometry, save_json, fingerprint
from twinguard.evaluation.geometric_studies import generate
from twinguard.evaluation.analytics import evaluate_e1, verify_seal
from twinguard.evaluation.geometric_revalidation import enrich, summarize, paired_bootstrap


def trial_worker(trial):
    root = Path.cwd()
    run = root / "experiments/outputs/phase3_1"
    output = run / "heldout-v1"
    config = AnalyticsConfig()
    reference = load_reference(root / "configs/analytics/accepted_reference.json")
    calibration = json.loads((run / "b31_calibration_v1.json").read_text())
    old = json.loads((run / "baseline-reproduction/geometry_calibration.json").read_text())
    case = trial["case_id"]
    data = output / "datasets" / case
    prediction = output / "predictions" / case
    reused = (prediction / "predictions_ready.json").exists()
    if reused:
        verify_seal(prediction)
    else:
        # Preserve any partial acquisition interrupted during the execution transition.
        for kind, path in [("data", data), ("prediction", prediction)]:
            if path.exists():
                dest = run / "interrupted-at-parallel-transition" / kind / case
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(dest))
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
        analyze_geometry(
            *paths,
            config,
            reference,
            prediction,
            old,
            methods=["B1", "B2", "B3", "B3.1"],
            improved_calibration=calibration,
        )
    rows = enrich(data, prediction, evaluate_e1(data, prediction, trial), trial)
    save_json(output / "trial_metrics" / f"{case}.json", rows)
    return rows, reused, os.getpid(), resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def main():
    root = Path.cwd()
    run = root / "experiments/outputs/phase3_1"
    output = run / "heldout-v1"
    if (output / "report.json").exists():
        raise ValueError("Completed held-out evaluation cannot be rerun")
    freeze = json.loads((root / "docs/phase3_1/improved_freeze.json").read_text())
    assert (
        fingerprint(json.loads((run / "b31_calibration_v1.json").read_text()))
        == freeze["calibration_sha256"]
    )
    for name, digest in freeze["source_sha256"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
    cases = []
    for seed in range(4100, 4130):
        for level in ["L0", "L1", "L2"]:
            for amplitude in [0, 0.01, 0.02, 0.03, 0.05]:
                for view in ["same", "changed"]:
                    cases.append(
                        {
                            "seed": seed,
                            "fidelity": level,
                            "amplitude_m": amplitude,
                            "viewpoint": view,
                        }
                    )
    for seed in range(4100, 4110):
        for view in ["partial", "high_pose", "low_overlap"]:
            cases.append({"seed": seed, "fidelity": "L2", "amplitude_m": 0.03, "viewpoint": view})
    for i, trial in enumerate(cases):
        trial["case_id"] = f"trial-{i:04d}"
    start = time.perf_counter()
    rows = []
    reused = 0
    peaks = {}
    with ProcessPoolExecutor(max_workers=3, mp_context=get_context("spawn")) as pool:
        jobs = [pool.submit(trial_worker, t) for t in cases]
        for job in as_completed(jobs):
            result, cached, pid, peak = job.result()
            rows.extend(result)
            reused += cached
            peaks[pid] = peak
            completed = len(rows) // 4
            if completed % 20 == 0:
                save_json(
                    output / "parallel_progress.json",
                    {
                        "completed": completed,
                        "planned": 930,
                        "parallel_runtime_s": time.perf_counter() - start,
                        "sealed_cases_reused": reused,
                    },
                )
                print("heldout parallel", completed, "/930", flush=True)
    rows.sort(key=lambda r: (r["case_id"], r["method"]))
    ended = datetime.now(timezone.utc)
    report = {
        "experiment_id": "E1-Phase3.1",
        "trials": 930,
        "principal_trials": 900,
        "stress_trials": 30,
        "seeds": list(range(4100, 4130)),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "software_version": __import__("twinguard").__version__,
        "freeze": freeze,
        "started_at": freeze["frozen_at"],
        "ended_at": ended.isoformat(),
        "rows": rows,
        "metrics": summarize(rows),
        "paired_comparison": paired_bootstrap(rows),
        "runtime_s": (ended - datetime.fromisoformat(freeze["frozen_at"])).total_seconds(),
        "parallel_runtime_s": time.perf_counter() - start,
        "max_worker_rss_mib": max(peaks.values()),
        "sum_worker_peak_rss_upper_bound_mib": sum(peaks.values()),
        "parent_peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        "sealed_cases_reused": reused,
        "execution_note": "Three isolated spawn workers, one OpenMP/BLAS thread each. Existing sealed sequential predictions reused unchanged; interrupted unsealed artifacts preserved separately. Runtime spans candidate freeze through final metrics, including transition/commit overhead. Frozen algorithm/model/cases unchanged.",
        "execution_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "statistical_note": "30 independent seeds per amplitude/noise cell, two paired views. Bootstrap resamples seeds. Engineering scores are not statistical confidence intervals.",
    }
    save_json(output / "report.json", report)
    save_json(root / "docs/phase3_1/heldout_results.json", report)
    print("HELDOUT COMPLETED", flush=True)


if __name__ == "__main__":
    main()
