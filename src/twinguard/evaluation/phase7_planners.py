"""Independent paired Phase 7 controller. Production planning never imports this module.

Plans and public results are sealed before restricted footprint evaluation. Identical
requested views share observations within a paired case; ablation runs use new output
roots and actually acquire again. No truth enters planning or F1.
"""

from pathlib import Path
from datetime import timedelta
from concurrent.futures import ProcessPoolExecutor
import copy
import hashlib
import json
import time
import resource
import numpy as np
from twinguard.analytics.config import AnalyticsConfig
from twinguard.analytics.pipeline import analyze_geometry, seal_predictions
from twinguard.analytics.reference import load_reference
from twinguard.analytics.clouds import load_scan
from twinguard.core.contracts import InspectionCapture
from twinguard.core.observations import load_public_observations
from twinguard.inspection.contracts import (
    PlanningSnapshot,
    BaselineInspectionSupport,
    InspectionPlanningRequest,
)
from twinguard.inspection.coverage import ReferenceSurface
from twinguard.inspection.observations import load_config, snapshot as public_states, fingerprint
from twinguard.inspection.candidates import generate
from twinguard.inspection.optimizer import plan
from twinguard.inspection.qualified_optimizer import select_plan
from twinguard.inspection.feasibility import route
from twinguard.fusion.engine import assess
from twinguard.fusion.models import FusionState
from twinguard.fusion.policies import load_policy
from twinguard.fusion import adapters
from twinguard.plant.config import load_plant_config
from twinguard.plant.model import create_baseline_plant
from twinguard.plant.simulator import PlantSimulator
from twinguard.sensing.acquisition import acquire, load_installation
from .experiments import setup_scenario
from .campaigns import Campaign, atomic_json, resource_preflight
from .inspection_experiments import coverage_result, processing
from .phase7_research import region_matches
from .analytics import verify_seal

FAMILIES = (
    "healthy_wide",
    "previously_unconfirmed",
    "partial_initial",
    "stale_initial",
    "L2",
    "load_transition",
    "competing_assets",
    "critical_access",
)
ABLATIONS = (
    "no_risk_priority",
    "no_coverage_history",
    "no_calibration_applicability",
    "no_registration_suitability",
    "no_redundancy_penalty",
    "no_adaptive_replanning",
)


def trial(task):
    root, output, family, seed, ablation = task
    root, output = Path(root), Path(output)
    case = f"{family}-{seed}" + (f"-{ablation}" if ablation else "")
    done = output / "completed_units" / (case + ".json")
    if done.exists():
        return json.loads(done.read_text())
    resource_preflight(reserve_bytes=48 * 1024**2)
    work = output / "trials" / case
    if work.exists():
        work = work.with_name(case + "-attempt-" + str(time.time_ns()))
    work.mkdir(parents=True)
    config = load_config(root / "configs/inspection/planner.yaml")
    # Geometric support is genuinely limited to BW; no substitute calibration for other assets.
    config.available_modalities = ["lidar"]
    level = "L2" if family == "L2" else "L1"
    config.sensor_path = f"configs/sensing/{level}.yaml"
    installation = load_installation(root / config.sensor_path)
    installation.event_poses = {}
    surface = ReferenceSurface(root / config.reference_path, config.reference_sha256, config.cell_m)
    amplitude = (
        0
        if family in ("healthy_wide", "stale_initial", "load_transition", "critical_access")
        else (0.01, 0.02, 0.03)[seed % 3]
    )
    scenario, faults = setup_scenario(
        root,
        case,
        seed,
        profile="increase" if family == "load_transition" else "steady",
        kind="geometric" if amplitude else None,
        amplitude=amplitude,
    )
    if faults:
        rng = np.random.default_rng(seed)
        faults[0].center_local_m = (
            float(rng.uniform(-0.35, 0.35)),
            0,
            float(rng.uniform(0.8, 1.55)),
        )
        faults[0].extent_m = (float(rng.uniform(0.28, 0.48)), 0.1, float(rng.uniform(0.35, 0.6)))
    simulator = PlantSimulator(
        create_baseline_plant(load_plant_config(root / "configs/plant.yaml"), seed),
        scenario,
        faults,
    )
    cache = {}

    def capture(pose, offset, narrow=False):
        key = fingerprint({"pose": pose.model_dump(mode="json"), "time": offset, "narrow": narrow})
        if key not in cache:
            inst = installation.model_copy(deep=True)
            matrix = np.asarray(pose.matrix).copy()
            rng = np.random.default_rng(seed + int(key[:8], 16))
            matrix[:3, 3] += rng.uniform(-0.025, 0.025, 3)
            inst.lidar.pose = pose.model_copy(update={"matrix": matrix.tolist()})
            if narrow:
                inst.lidar.horizontal_fov_rad = 0.30
            path = work / "captures" / key[:16]
            acquire(
                simulator.sensing_reader(), scenario, inst, path, modality="lidar", time_s=offset
            )
            c = next(v for v in load_public_observations(path) if isinstance(v, InspectionCapture))
            cache[key] = path, c
        return cache[key]

    baseline_root, baseline = capture(installation.lidar.pose, 0)
    initial_root, initial = capture(
        installation.lidar.pose, 60, family in ("partial_initial", "previously_unconfirmed")
    )
    model = json.loads((root / "configs/fusion/calibration/geometry_b31.json").read_text())
    bundle = json.loads((root / "configs/validation/view_calibration.json").read_text())
    reference = load_reference(root / "configs/analytics/accepted_reference.json")
    policy = load_policy(root / "configs/fusion/hazards.yaml")
    initial_reports = analyze_geometry(
        baseline_root / baseline.artifact.uri,
        initial_root / initial.artifact.uri,
        AnalyticsConfig(),
        reference,
        work / "initial-analysis",
        methods=["B3.1", "B3.2"],
        improved_calibration=model,
        view_calibration=bundle,
    )
    baseline_cloud = load_scan(baseline_root / baseline.artifact.uri, AnalyticsConfig())
    bs = surface.observed(
        "BW-01",
        baseline_cloud.processing_world_m,
        baseline.acquired_at,
        baseline.received_at,
        baseline.capture_id,
        False,
        False,
        1,
        [],
    )
    support = BaselineInspectionSupport(
        capture_id=baseline.capture_id,
        reference_hash=surface.hash,
        reported_pose=baseline.sensor_pose,
        acquired_at=baseline.acquired_at,
        available_at=baseline.received_at,
        acquisition_parameters={
            k: v
            for k, v in baseline.acquisition_parameters.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        },
        observed_cells=bs.observed_cells,
    )
    rows = []
    pending = []
    methods = ("P3v2",) if ablation else ("P0", "P1", "P2", "P3", "P3v2")
    for detector in ("B3.1", "B3.2"):
        reg, geom = initial_reports[detector]
        at = initial.received_at + timedelta(seconds=2)
        evidence = adapters.geometry(geom, reg, processing(geom, at), initial.provenance_id)
        state, traces = assess(FusionState(), evidence, policy, at)
        cov = coverage_result(
            surface,
            initial_root,
            initial,
            reg,
            geom,
            at,
            work / f"initial-analysis/{detector}/registered_current.npz",
        )
        states = public_states(
            at,
            sorted(set(surface.assets)),
            {t.assessment.asset_id: t.model_dump(mode="json") for t in traces},
            [e.model_dump(mode="json") for e in state.events.values()],
        )
        if family == "competing_assets":
            # Public risk metadata only. Unsupported alternate asset remains explicit.
            for a in states:
                if a.asset_id == "DR-01":
                    a.reinspection = True
        if family == "critical_access":
            # Declared operational policy control, NOT a measured pressure event.
            config.restricted_assets = ["BW-01"]
        snap = PlanningSnapshot(
            snapshot_id=case + detector.replace(".", ""),
            at=at,
            reference_hash=surface.hash,
            assets=states,
            coverage=[cov],
            baseline_support=support,
            input_refs=[geom.analysis_id, reg.registration_id, initial.capture_id],
        )
        if family == "stale_initial":
            # Leave source timestamps intact: evaluate genuinely aged evidence at a later decision time.
            snap.at += timedelta(seconds=7200)
        candidates = generate(surface, snap, config, root)
        atomic_json(work / detector / "initial-snapshot.json", snap.model_dump(mode="json"))
        for method in methods:
            start = time.perf_counter()
            cpu = time.process_time()
            destination = work / detector / method
            current = snap.model_copy(deep=True)
            fs = copy.deepcopy(state)
            request = InspectionPlanningRequest(
                request_id=f"{case}-{method}-{detector}", method=method, budget_views=2, budget_s=70
            )

            def choose(c, r, cfg):
                return (
                    select_plan(
                        surface,
                        c,
                        cfg,
                        r,
                        candidates,
                        bundle,
                        root,
                        ablation=ablation if ablation != "no_adaptive_replanning" else None,
                    )
                    if method == "P3v2"
                    else plan(surface, c, cfg, r, candidates)
                )

            frozen = choose(current, request, config)
            atomic_json(destination / "plan.json", frozen.model_dump(mode="json"))
            seal_predictions(
                destination,
                {"method": method, "detector": detector, "ablation": ablation},
                [fingerprint(snap)],
            )
            adaptive = method in ("P3", "P3v2") and ablation != "no_adaptive_replanning"
            steps = list(frozen.steps[:1] if adaptive else frozen.steps)
            qualified = set(cov.qualified_cells)
            initial_qualified = set(qualified)
            analyses = []
            total_cost = 0.0
            position = np.asarray(config.start_world_m)
            executed = 0
            for index in range(request.budget_views):
                if index >= len(steps):
                    break
                step = steps[index]
                chosen = next(v for v in candidates if v.viewpoint_id == step.viewpoint_id)
                target = np.asarray(chosen.planned_pose.matrix)[:3, 3]
                travel = float(np.linalg.norm(target - position))
                home = float(np.linalg.norm(target - config.start_world_m))
                cost = travel / config.speed_m_s + chosen.acquisition_s
                if total_cost + cost + home / config.speed_m_s > request.budget_s or not route(
                    surface, position, target, config
                ):
                    break
                # The frozen plan is persisted and sealed BEFORE original sensing is invoked.
                path, acquired = capture(chosen.planned_pose, 62 + index * 8)
                pred = destination / f"analysis-{index}"
                r, g = analyze_geometry(
                    baseline_root / baseline.artifact.uri,
                    path / acquired.artifact.uri,
                    AnalyticsConfig(),
                    reference,
                    pred,
                    methods=[detector],
                    improved_calibration=model,
                    view_calibration=bundle,
                )[detector]
                available = max(current.at, acquired.received_at) + timedelta(seconds=1)
                coverage = coverage_result(
                    surface,
                    path,
                    acquired,
                    r,
                    g,
                    available,
                    pred / detector / "registered_current.npz",
                )
                qualified.update(coverage.qualified_cells)
                ev = adapters.geometry(g, r, processing(g, available), acquired.provenance_id)
                fs, ts = assess(fs, ev, policy, available)
                analyses.append((g, r, chosen.viewpoint_id))
                current.coverage.append(coverage)
                current.at = available
                current.previous_plan_id = frozen.plan_id
                current.attempted_viewpoints.append(chosen.viewpoint_id)
                current.assets = public_states(
                    available,
                    sorted(set(surface.assets)),
                    {t.assessment.asset_id: t.model_dump(mode="json") for t in ts},
                    [e.model_dump(mode="json") for e in fs.events.values()],
                )
                total_cost += cost
                position = target
                executed += 1
                if adaptive and index + 1 < request.budget_views:
                    cfg = config.model_copy(update={"start_world_m": tuple(target)})
                    req = request.model_copy(
                        update={
                            "budget_views": 1,
                            "budget_s": max(0.001, request.budget_s - total_cost),
                        }
                    )
                    nextplan = choose(current, req, cfg)
                    atomic_json(
                        destination / f"replan-{index}.json", nextplan.model_dump(mode="json")
                    )
                    seal_predictions(
                        destination / f"replan-seal-{index}",
                        {"plan_hash": fingerprint(nextplan)},
                        [fingerprint(current)],
                    )
                    if nextplan.steps:
                        steps.append(nextplan.steps[0])
            if executed:
                total_cost += (
                    float(np.linalg.norm(position - config.start_world_m)) / config.speed_m_s
                )
            atomic_json(destination / "F1.json", fs.model_dump(mode="json"))
            atomic_json(
                destination / "results.json",
                [
                    {
                        "geometry": g.model_dump(mode="json"),
                        "registration": r.model_dump(mode="json"),
                        "viewpoint_id": v,
                    }
                    for g, r, v in analyses
                ],
            )
            seal_predictions(
                destination,
                {"method": method, "detector": detector, "ablation": ablation},
                [fingerprint(snap)],
            )
            verify_seal(destination)
            row = dict(
                case_id=case,
                family=family,
                seed=seed,
                method=method,
                detector=detector,
                ablation=ablation,
                amplitude_m=amplitude,
                views=executed,
                plan_status=frozen.status,
                initial_status=geom.status,
                initial_positive=geom.significant is True,
                initial_qualified_area_m2=surface.area_of(initial_qualified),
                new_qualified_area_m2=surface.area_of(qualified - initial_qualified),
                cumulative_qualified_area_m2=surface.area_of(qualified),
                inconclusive=sum(g.status != "valid" for g, _, _ in analyses),
                registration_failures=sum(r.status != "valid" for _, r, _ in analyses),
                calibration_applicable=sum(
                    g.calibration_id != "uncalibrated-view-domain" for g, _, _ in analyses
                ),
                mission_proxy_s=total_cost,
                wall_s=time.perf_counter() - start,
                cpu_s=time.process_time() - cpu,
                rss_peak_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                plan_hash=fingerprint(frozen),
                snapshot_hash=fingerprint(snap),
                critical_policy_control=family == "critical_access",
                multi_asset_limit="BW calibration only",
                previously_unconfirmed=geom.significant is not True,
            )
            pending.append((row, geom, analyses))
    # Only this restricted evaluator obtains footprint labels after ALL methods are sealed.
    truth = simulator.ground_truth_at(60, case).model_dump(mode="json")
    atomic_json(work / "evaluation_private/truth.json", truth)
    fault = next((f for f in truth.get("fault_states", []) if f.get("asset_id") == "BW-01"), None)
    for row, initial_geometry, analyses in pending:
        im = region_matches(initial_geometry, fault)
        matches = [region_matches(g, fault) for g, _, _ in analyses]
        row.update(
            initial_localized=any(im),
            new_localized=any(any(m) for m in matches),
            cumulative_localized=any(im) or any(any(m) for m in matches),
            confirmation=any(im) and any(any(m) for m in matches),
            positive_regions=sum(len(m) for m in matches),
            matched_regions=sum(sum(m) for m in matches),
            healthy_false_positive=not amplitude and any(len(m) > 0 for m in matches),
        )
        rows.append(row)
    atomic_json(done, rows)
    return rows


def run(root, output, partition="development", workers=2, ablations=False, resume=False):
    root, output = Path(root).resolve(), Path(output).resolve()
    settings = json.loads((root / "configs/validation/phase7.yaml").read_text())
    seeds = (
        settings["development_seeds"][:2]
        if partition == "development"
        else settings["heldout_seeds"]
    )
    tasks = [
        (str(root), str(output), family, seed, ablation)
        for seed in seeds
        for family in (("previously_unconfirmed",) if ablations else FAMILIES)
        for ablation in (ABLATIONS if ablations else (None,))
    ]
    sources = {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ("inspection", "analytics", "fusion", "sensing", "evaluation")
        for p in sorted((root / "src/twinguard" / folder).glob("*.py"))
    }
    campaign = Campaign(
        output,
        {
            "purpose": "Phase7 paired planners and real acquisition ablations",
            "partition": partition,
            "seeds": seeds,
            "families": FAMILIES,
            "ablations": ablations,
            "source_hashes": sources,
            "model_sha256": hashlib.sha256(
                (root / "configs/validation/view_calibration.json").read_bytes()
            ).hexdigest(),
            "count": len(tasks),
            "limitations": [
                "Synthetic software only",
                "critical_access is declared policy control, not measured process pressure",
                "competing assets lack equivalent geometric calibration",
                "No independent environmental occluder or sufficient-scoped-coverage control implemented in this campaign",
                "Mission time is engineering proxy; actual compute timing reported separately",
            ],
        },
        resume=resume,
    )
    todo = [
        t
        for t in tasks
        if f"{t[2]}-{t[3]}" + (f"-{t[4]}" if t[4] else "") not in campaign.state["completed"]
    ]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for values in pool.map(trial, todo):
            campaign.commit(values[0]["case_id"], values)
    campaign.finish(len(tasks))
    return output
