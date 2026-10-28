"""Replay every sealed E3 stream after non-decision representation corrections.

Original observations/results remain immutable. The engine receives only verified
public evidence, public per-case policy and controlled public operator actions.
Every ConditionAssessment semantic field, event, source selection and compatibility
result must equal the original run; only IDs/hashes and explanation text may differ.
"""

from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import get_context
from datetime import datetime
import json
import time
import resource
import shutil
import subprocess
import hashlib
from twinguard.fusion.models import FusionPolicy
from twinguard.fusion.engine import replay
from twinguard.fusion.io import read_evidence, save_evidence, write_run, save
from twinguard.evaluation.fusion_scenarios import controlled
from twinguard.evaluation.fusion_experiments import schedule
from twinguard.evaluation.fusion_metrics import evaluate_case, summarize
from twinguard.evaluation.analytics import verify_seal

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "experiments/outputs/phase4-full"
OUTPUT = ROOT / "experiments/outputs/phase4-validated"


def semantic(history):
    result = []
    for d in history:
        assessment = dict(d["assessment"])
        assessment.pop("assessment_id")
        result.append(
            {
                "assessment": assessment,
                **{
                    key: d[key]
                    for key in [
                        "method",
                        "triggered_hazards",
                        "positive_ids",
                        "historical_positive_ids",
                        "negative_ids",
                        "missing_requirements",
                        "rejected_ids",
                        "temporal",
                        "compatibility",
                        "conflicts",
                        "event_ids",
                        "replay_mode",
                    ]
                },
            }
        )
    return result


def worker(arg):
    track, case_id, seed, condition = arg
    old = SOURCE / track / case_id
    new = OUTPUT / track / case_id
    evidence = read_evidence(old / "inputs")
    save_evidence(
        new / "inputs",
        evidence,
        {
            "source_manifest": str(old / "inputs/manifest.json"),
            "validation_revision": "representation-v3-persistence",
        },
    )
    policy = FusionPolicy.model_validate_json((old / "F1/policy.json").read_text())
    actions = []
    if track == "controlled":
        # Designed public action schedule, not simulator truth or a condition selector in the engine.
        _, actions, _, _, _ = controlled(int(condition.split("C")[-1]), seed, policy)
    save(new / "inputs/actions.json", [a.model_dump(mode="json") for a in actions])
    rows = []
    measurements = {}
    comparisons = 0
    for method in ["F0", "F1"]:
        verify_seal(old / method)
        previous = json.loads((old / method / "history.json").read_text())
        end = datetime.fromisoformat(
            previous[-1]["assessment"]["assessed_at"].replace("Z", "+00:00")
        )
        started = time.perf_counter()
        if track == "controlled":
            state, history = replay(evidence, policy, end, actions, method=method)
        else:
            state, history = schedule(evidence, policy, end, method, 5)
        duration = time.perf_counter() - started
        measurements[method] = duration
        actual = [d.model_dump(mode="json") for d in history]
        if semantic(actual) != semantic(previous):
            raise AssertionError("Decision semantics changed: " + case_id + " " + method)
        previous_events = json.loads((old / method / "events.json").read_text())
        assert [e.model_dump(mode="json") for e in state.events.values()] == previous_events, (
            "Event lifecycle changed"
        )
        comparisons += len(actual)
        write_run(
            new / method,
            state,
            history,
            policy,
            {
                "source_prediction_run": str(old / method),
                "validation_revision": "representation-v3-persistence",
                "processing_runtime_s": duration,
                "mode": "online",
            },
        )
    # Only after the new predictions have been saved and sealed are evaluator labels read.
    for method in ["F0", "F1"]:
        verify_seal(new / method)
    private = new / "evaluation_private"
    private.mkdir(mode=0o700)
    shutil.copy2(old / "evaluation_private/label.json", private / "label.json")
    (private / "label.json").chmod(0o600)
    label = json.loads((private / "label.json").read_text())
    for method in ["F0", "F1"]:
        result = evaluate_case(new / method, label)
        rows.append(
            {
                "track": "controlled" if track == "controlled" else "end_to_end",
                "case_id": case_id,
                "seed": seed,
                "condition": condition,
                "method": method,
                "fusion_runtime_s": measurements[method],
                **result,
            }
        )
    save(private / "metrics.json", rows)
    return rows, comparisons, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def main():
    if OUTPUT.exists():
        raise ValueError("Validated replay output must be new/empty")
    OUTPUT.mkdir(parents=True)
    original = json.loads((SOURCE / "report.json").read_text())
    jobs = []
    for track in ["controlled", "end_to_end"]:
        for row in original[track]["rows"]:
            if row["method"] == "F0":
                jobs.append((track, row["case_id"], row["seed"], row["condition"]))
    rows = []
    total = 0
    peak = 0
    start = time.perf_counter()
    with ProcessPoolExecutor(max_workers=3, mp_context=get_context("spawn")) as pool:
        futures = [pool.submit(worker, arg) for arg in jobs]
        for future in as_completed(futures):
            result, count, memory = future.result()
            rows += result
            total += count
            peak = max(peak, memory)
            if len(rows) % 100 == 0:
                print("Revalidated identical decisions", len(rows) // 2, "/", len(jobs), flush=True)
    report = {
        **{k: v for k, v in original.items() if k not in ["controlled", "end_to_end", "runtime_s"]},
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_observation_run": str(SOURCE),
        "initial_sensor_analytics_runtime_s": original["runtime_s"],
        "validation_replay_runtime_s": time.perf_counter() - start,
        "runtime_s": original["runtime_s"] + time.perf_counter() - start,
        "assessments_semantically_identical": total,
        "max_replay_worker_rss_mib": peak,
        "validation_revision": "representation-v3-persistence",
        "corrections": "Canonical semantic policy hashing; explicit active-recovery/unknown-scope rationale; standalone prepare-format compatibility; audit counts distinguish current triggered-rule eligibility from historical support. Consecutive activation candidates are now reset by an intervening qualified normal. Shipped rule parameters, eligibility decisions, severities, events, actions, evidence selections and timings unchanged on the complete E3 corpus.",
        "validated_source_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT / "src/twinguard/fusion").glob("*.py"))
        },
    }
    for track in ["controlled", "end_to_end"]:
        selected = sorted(
            [r for r in rows if r["track"] == track], key=lambda r: (r["case_id"], r["method"])
        )
        report[track] = {
            "cases": len(selected) // 2,
            "metrics": summarize(selected),
            "rows": selected,
        }
        old = {(r["case_id"], r["method"]): r for r in original[track]["rows"]}
        for r in selected:
            for key in [
                "positive",
                "detected",
                "any_advisory",
                "critical",
                "red",
                "event_matched",
                "unmatched_advisory",
                "delay_s",
                "final_severity",
                "unknown_fraction",
            ]:
                assert r[key] == old[r["case_id"], r["method"]][key], (r["case_id"], key)
    save(OUTPUT / "report.json", report)
    print("ALL E3 DECISION/EVENT/MATCHING EQUIVALENCE CHECKS PASSED", flush=True)


if __name__ == "__main__":
    main()
