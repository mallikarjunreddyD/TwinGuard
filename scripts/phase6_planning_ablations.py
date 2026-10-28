"""Post-freeze planning-only component ablations. No acquisition/detection benefit inferred."""

from pathlib import Path
import json
from twinguard.inspection.contracts import (
    PlanningConfig,
    PlanningSnapshot,
    InspectionPlanningRequest,
    CandidateViewpoint,
)
from twinguard.inspection.coverage import ReferenceSurface
from twinguard.inspection.optimizer import plan
from twinguard.inspection.observations import load_config, fingerprint
from twinguard.analytics.pipeline import save_json

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/outputs/phase6-E5-recovered/shard-2"


def main():
    config = load_config(ROOT / "configs/inspection/planner.yaml")
    surface = ReferenceSurface(ROOT / config.reference_path, config.reference_sha256, config.cell_m)
    rows = []
    for trial in sorted(BASE.glob("E5-S03-*")):
        snapshot = PlanningSnapshot.model_validate_json(
            (trial / "initial-snapshot.json").read_text()
        )
        pool = [
            CandidateViewpoint.model_validate(v)
            for v in json.loads((trial / "candidates.json").read_text())
        ]
        original = json.loads((trial / "P3/plan.json").read_text())
        request = InspectionPlanningRequest.model_validate(original["request"])
        for variant in (
            "full",
            "no_risk_utility",
            "no_coverage_history",
            "no_suitability_term",
            "no_redundancy_penalty",
            "no_freshness_priority",
        ):
            c = PlanningConfig.model_validate_json((trial / "config.json").read_text())
            s = snapshot.model_copy(deep=True)
            if variant == "no_coverage_history":
                s.coverage = []
            elif variant == "no_freshness_priority":
                c.priority_weights["freshness"] = 0
                total = sum(c.priority_weights.values())
                c.priority_weights = {k: v / total for k, v in c.priority_weights.items()}
            elif variant != "full":
                term = {
                    "no_risk_utility": "risk",
                    "no_suitability_term": "suitability",
                    "no_redundancy_penalty": "redundancy",
                }[variant]
                c.utility_weights[term] = 0
                total = sum(c.utility_weights.values())
                c.utility_weights = {k: v / total for k, v in c.utility_weights.items()}
            outcome = plan(surface, s, c, request, pool)
            rows.append(
                {
                    "trial": trial.name,
                    "variant": variant,
                    "source_snapshot_hash": fingerprint(snapshot),
                    "candidate_pool_hash": fingerprint([v.model_dump(mode="json") for v in pool]),
                    "budget_s": request.budget_s,
                    "views": len(outcome.steps),
                    "predicted_usable_new_area_m2": outcome.expected_new_usable_area_m2,
                    "viewpoint_ids": [v.viewpoint_id for v in outcome.steps],
                    "runtime_s": outcome.optimization_runtime_s,
                }
            )
        executed = json.loads((trial / "P3/executed-steps.json").read_text())
        rows.append(
            {
                "trial": trial.name,
                "variant": "no_adaptive_execution_comparison",
                "frozen_static_viewpoints": [v["viewpoint_id"] for v in original["steps"]],
                "actually_adaptive_viewpoints": [v["viewpoint_id"] for v in executed],
            }
        )
    save_json(
        ROOT / "docs/phase6/ablation_planning.json",
        {
            "scope": "30 same held-out S03 public snapshots; planning-only post-freeze ablations; actual acquisitions were not rerun, so expected score changes are not causal detection evidence. Hard calibration/safety constraints and coverage union remain enforced.",
            "rows": rows,
        },
    )
    print("Ablation records", len(rows), flush=True)


if __name__ == "__main__":
    main()
