"""Fair candidate pool, deterministic greedy marginal selection and bounded exact reference."""

import time
from itertools import permutations
import numpy as np
from .contracts import InspectionPlan, InspectionPlanStep, PlanningExplanation
from .observations import fingerprint
from .coverage import qualified_history
from .priority import priorities
from .utility import utility
from .feasibility import route


def plan(surface, snapshot, config, request, candidates):
    started = time.perf_counter()
    if snapshot.reference_hash != surface.hash or config.reference_sha256 != surface.hash:
        raise ValueError("Reference mismatch")
    ranks = priorities(surface, snapshot, config)
    rank = {p.asset_id: p for p in ranks}
    covered = qualified_history(surface, snapshot, config)
    initial = set(covered)
    position = np.array(config.start_world_m)
    duration = 0.0
    distance = 0.0
    steps = []
    counts = {}
    remaining = [
        v.model_copy(deep=True)
        for v in candidates
        if v.feasibility.status == "feasible"
        and v.viewpoint_id not in snapshot.attempted_viewpoints
    ]
    for _ in range(request.budget_views):
        options = []
        for v in remaining:
            target = np.asarray(v.planned_pose.matrix)[:3, 3]
            travel = float(np.linalg.norm(target - position))
            home = (
                float(np.linalg.norm(target - config.start_world_m))
                if config.return_to_start
                else 0
            )
            if counts.get(v.asset_id, 0) >= request.per_asset_limit:
                continue
            if (
                duration + travel / config.speed_m_s + v.acquisition_s + home / config.speed_m_s
                > request.budget_s
                or distance + travel + home > request.maximum_travel_m
            ):
                continue
            if not route(surface, position, target, config) or (
                config.return_to_start and not route(surface, target, config.start_world_m, config)
            ):
                continue
            u = utility(
                v,
                covered,
                surface,
                rank[v.asset_id],
                config,
                travel / config.speed_m_s,
                request.budget_s,
            )
            if not u.new_cells:
                continue
            if request.method == "P3" and (
                u.score <= 0 or rank[v.asset_id].terms["deficiency"] <= 1e-8
            ):
                continue
            score = (
                u.score
                if request.method == "P3"
                else surface.area_of(u.new_cells)
                if request.method == "P1"
                else rank[v.asset_id].terms["severity"] + rank[v.asset_id].terms["criticality"]
                if request.method == "P2"
                else 0
            )
            options.append((score, v.viewpoint_id, v, u, travel, target))
        if not options:
            break
        options.sort(key=lambda x: (-x[0], x[1]))
        _, _, v, u, travel, target = options[0]
        v.utility = u
        steps.append(
            InspectionPlanStep(
                order=len(steps) + 1,
                viewpoint_id=v.viewpoint_id,
                asset_id=v.asset_id,
                travel_m=travel,
                travel_s=travel / config.speed_m_s,
                acquisition_s=v.acquisition_s,
                marginal_area_m2=surface.area_of(u.new_cells),
                utility=u,
            )
        )
        covered.update(u.new_cells)
        duration += travel / config.speed_m_s + v.acquisition_s
        distance += travel
        position = target
        counts[v.asset_id] = counts.get(v.asset_id, 0) + 1
        remaining = [x for x in remaining if x.viewpoint_id != v.viewpoint_id]
    if steps and config.return_to_start:
        home = float(np.linalg.norm(position - config.start_world_m))
        distance += home
        duration += home / config.speed_m_s
    selected = {s.viewpoint_id: s for s in steps}
    copies = [v.model_copy(deep=True) for v in candidates]
    for v in copies:
        if v.viewpoint_id in selected:
            v.utility = selected[v.viewpoint_id].utility
    status = (
        "recommended"
        if steps
        else "requires_route_review"
        if any(v.feasibility.status == "requires_route_review" for v in candidates)
        else "continue_monitoring"
        if ranks and all(p.terms["deficiency"] <= 1e-8 for p in ranks)
        else "no_viable_viewpoint"
    )
    explanation = PlanningExplanation(
        selected=[
            f"{s.viewpoint_id}: marginal {s.marginal_area_m2:.6f} m2; components {s.utility.terms}"
            for s in steps
        ],
        rejected={
            v.viewpoint_id: v.feasibility.reasons
            if v.feasibility.status != "feasible"
            else [
                "Already attempted, redundant, budget/route constrained, or lower marginal utility"
            ]
            for v in copies
            if v.viewpoint_id not in selected
        },
        limitations=[
            "Expected coverage is not measured or qualified evidence",
            "Static sampled corridor is not certified collision avoidance",
            "B3.1 relative wall change only; L2 precision cannot be repaired by viewpoint changes",
            "Thermal image-only findings cannot identify a 3D hotspot",
            "All recommendations require operator review; no flight or process commands",
        ],
        recommended_actions=[
            "Explicit operator approval required before any critical-process close-range workflow"
            if any(a.critical_process for a in snapshot.assets)
            else "Review map, sensor support and proposed route before any inspection",
            "Use supported alternative sensing or authorized manual inspection when no viable view exists",
        ],
    )
    return InspectionPlan(
        plan_id="plan-"
        + fingerprint(
            [fingerprint(snapshot), fingerprint(config), request.model_dump(mode="json")]
        )[:24],
        at=snapshot.at,
        snapshot_hash=fingerprint(snapshot),
        policy_hash=fingerprint(config),
        request=request,
        priorities=ranks,
        candidates=copies,
        steps=steps,
        estimated_duration_s=duration,
        estimated_travel_m=distance,
        expected_new_usable_area_m2=surface.area_of(covered - initial),
        expected_deficiency_reduction=min(
            1, surface.area_of(covered - initial) / max(float(surface.area.sum()), 1e-12)
        ),
        targeted_assets=sorted(counts),
        relevant_advisories=sorted({i for a in snapshot.assets for i in a.advisory_ids}),
        status=status,
        explanation=explanation,
        optimization_runtime_s=time.perf_counter() - started,
        previous_plan_id=snapshot.previous_plan_id,
    )


def exact_coverage(surface, candidates, config, request, initial=()):
    """Exhaustive route-constrained maximum-area reference, <=8 views /3 selected."""
    viable = [v for v in candidates if v.feasibility.status == "feasible"]
    if len(viable) > 8 or request.budget_views > 3:
        raise ValueError("Exact optimizer safe limit is 8 candidates and 3 views")
    best = (0.0, ())
    for n in range(1, min(len(viable), request.budget_views) + 1):
        for sequence in permutations(viable, n):
            position = np.array(config.start_world_m)
            duration = 0.0
            distance = 0.0
            covered = set(initial)
            valid = True
            counts = {}
            for v in sequence:
                target = np.asarray(v.planned_pose.matrix)[:3, 3]
                d = float(np.linalg.norm(target - position))
                counts[v.asset_id] = counts.get(v.asset_id, 0) + 1
                if counts[v.asset_id] > request.per_asset_limit or not route(
                    surface, position, target, config
                ):
                    valid = False
                    break
                duration += d / config.speed_m_s + v.acquisition_s
                distance += d
                position = target
                covered.update(v.predicted_usable_cells)
            if config.return_to_start:
                d = float(np.linalg.norm(position - config.start_world_m))
                duration += d / config.speed_m_s
                distance += d
                valid = valid and route(surface, position, config.start_world_m, config)
            if valid and duration <= request.budget_s and distance <= request.maximum_travel_m:
                score = surface.area_of(covered - set(initial))
                ids = tuple(v.viewpoint_id for v in sequence)
                if score > best[0] + 1e-12:
                    best = (score, ids)
    return {
        "area_m2": best[0],
        "viewpoint_ids": list(best[1]),
        "objective": "maximum marginal usable area; not P3 utility",
    }
