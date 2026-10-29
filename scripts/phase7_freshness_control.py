"""Fresh acquisition after a genuinely aged initial record: separate frozen control.

The main stale_initial case is a late-delivery control, not proof of a fresh scan.
Here initial records keep their original timestamps, decision time ages naturally,
and original sensing actually acquires at t=7272/7280, after the approximately t=7262 decision.
No public measurement timestamp is rewritten. Production candidates stay frozen.
"""

from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
import argparse
import json
import hashlib
import time
import twinguard.evaluation.phase7_planners as controller
from twinguard.evaluation.campaigns import Campaign, atomic_json, digest

ROOT = Path(__file__).resolve().parents[1]


def one(task):
    output, seed = task
    output = Path(output)
    original_setup = controller.setup_scenario
    original_acquire = controller.acquire

    def setup(*args, **kwargs):
        scenario, faults = original_setup(*args, **kwargs)
        if faults:
            raise ValueError("Healthy chronology control must not contain faults")
        scenario.duration_s = 7400
        return scenario, faults

    def acquire(reader, scenario, installation, path, **kwargs):
        if kwargs.get("time_s", 0) >= 62:
            kwargs["time_s"] += 7210
        return original_acquire(reader, scenario, installation, path, **kwargs)

    controller.setup_scenario = setup
    controller.acquire = acquire
    try:
        rows = controller.trial((str(ROOT), str(output), "stale_initial", seed, None))
        trials = output / "trials"
        for row in rows:
            possible = [
                trials / f"stale_initial-{seed}",
                *trials.glob(f"stale_initial-{seed}-attempt-*"),
            ]
            work = next(
                (
                    d
                    for d in possible
                    if (d / row["detector"] / row["method"] / "plan.json").is_file()
                    and controller.fingerprint(
                        json.loads((d / row["detector"] / row["method"] / "plan.json").read_text())
                    )
                    == row["plan_hash"]
                ),
                None,
            )
            if work is None:
                raise ValueError("Cannot bind chronology result to frozen plan")
            snap = json.loads((work / row["detector"] / "initial-snapshot.json").read_text())
            results = json.loads(
                (work / row["detector"] / row["method"] / "results.json").read_text()
            )
            decision = datetime.fromisoformat(snap["at"].replace("Z", "+00:00"))
            times = [
                datetime.fromisoformat(r["geometry"]["acquired_at"].replace("Z", "+00:00"))
                for r in results
            ]
            if any(t < decision for t in times):
                raise ValueError("Reinspection acquisition precedes decision")
            row["chronology_control"] = "fresh_after_aged_initial"
            row["decision_at"] = snap["at"]
            row["new_acquired_at"] = [t.isoformat() for t in times]
            row["case_id"] = f"fresh_after_aged-{seed}"
        return rows
    finally:
        controller.setup_scenario = original_setup
        controller.acquire = original_acquire


def main(output, smoke=False, resume=False):
    output = output.resolve()
    seeds = list(range(17301, 17302) if smoke else range(17200, 17230))
    config = {
        "purpose": __doc__,
        "seeds": seeds,
        "count": len(seeds),
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "original_controller_sha256": hashlib.sha256(
            Path(controller.__file__).read_bytes()
        ).hexdigest(),
        "candidates": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for f in ("analytics", "inspection", "fusion", "sensing")
            for p in sorted((ROOT / "src/twinguard" / f).glob("*.py"))
        },
        "maximum_new_campaign_bytes": 6 * 1024**3,
    }
    if resume:
        state = json.loads((output / "campaign.json").read_text())
        before = json.loads(json.dumps(state))
        old = dict(state["configuration"])
        new = dict(config)
        old_source = old.pop("source_sha256")
        new_source = new.pop("source_sha256")
        if old != new:
            raise ValueError("Chronology/scientific configuration changed; cannot resume")
        atomic_json(output / f"campaign.before-memory-resume-{time.time_ns()}.json", before)
        state.setdefault("infrastructure_resumes", []).append(
            {
                "reason": "ENOMEM on external file reads; all other scientific campaigns quiesced, one case per fresh process, preserved-plan lookup for interrupted attempts",
                "old_source": old_source,
                "new_source": new_source,
                "prior_configuration_hash": state["configuration_hash"],
            }
        )
        state["configuration"] = config
        state["configuration_hash"] = digest(config)
        atomic_json(output / "campaign.json", state)
    campaign = Campaign(output, config, resume=resume)
    todo = [seed for seed in seeds if f"fresh_after_aged-{seed}" not in campaign.state["completed"]]
    try:
        for begin in range(0, len(todo), 1):
            with ProcessPoolExecutor(max_workers=1) as pool:
                for result in pool.map(one, [(str(output), s) for s in todo[begin : begin + 1]]):
                    campaign.commit(result[0]["case_id"], result)
        campaign.finish(len(seeds))
    except Exception as exc:
        campaign.fail(exc)
        raise
    atomic_json(output / "source_configuration.json", config)
    print(output)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--resume", action="store_true")
    a = p.parse_args()
    main(a.output, a.smoke, a.resume)
