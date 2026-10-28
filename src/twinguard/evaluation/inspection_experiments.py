"""Restricted E5 controller/evaluator. Planner imports none of this module.
Plans are written/sealed before acquisition; evaluation labels are read only after result seals.
"""

from datetime import timedelta
import json
import time
import copy
import subprocess
import hashlib
import numpy as np
from twinguard.inspection.contracts import (
    PlanningSnapshot,
    AssetPlanningState,
    InspectionPlanningRequest,
    Box,
)
from twinguard.inspection.observations import load_config, fingerprint, snapshot as public_states
from twinguard.inspection.coverage import ReferenceSurface
from twinguard.inspection.candidates import generate
from twinguard.inspection.optimizer import plan, exact_coverage
from twinguard.analytics.config import AnalyticsConfig
from twinguard.analytics.reference import load_reference
from twinguard.analytics.pipeline import analyze_geometry, save_json, seal_predictions
from twinguard.analytics.clouds import load_scan
from twinguard.analytics.thermal import infer_thermal
from twinguard.core.contracts import InspectionSchedule, InspectionCapture
from twinguard.core.observations import load_public_observations
from twinguard.fusion.engine import assess
from twinguard.fusion.models import ProcessingRecord, FusionState
from twinguard.fusion.policies import load_policy
from twinguard.fusion import adapters
from twinguard.plant.model import create_baseline_plant
from twinguard.plant.config import load_plant_config
from twinguard.plant.simulator import PlantSimulator
from twinguard.sensing.acquisition import acquire, load_installation
from .experiments import setup_scenario

SCENARIOS = {
    "E5-S01": "healthy_recent",
    "E5-S02": "healthy_stale",
    "E5-S03": "localized_warning",
    "E5-S04": "partial_initial",
    "E5-S05": "L2",
    "E5-S06": "partial_occlusion",
    "E5-S07": "competing_needs",
    "E5-S08": "thermal_image_only",
    "E5-S09": "pressure_warning",
    "E5-S10": "critical_restricted",
    "E5-S11": "overlap",
    "E5-S12": "no_feasible",
    "E5-S13": "registration_unsupported",
    "E5-S14": "uncalibrated_range",
    "E5-S15": "remains_inconclusive",
    "E5-S16": "missing_metadata",
    "E5-S17": "tight_budget",
    "E5-S18": "no_go_route",
}


def processing(result, at):
    return ProcessingRecord(
        source_id=result.analysis_id,
        received_at=at,
        processed_at=at,
        available_at=at,
        basis="simulated_replay",
        rationale="Explicit software trial availability, not physical latency",
        clock_quality="synchronized",
    )


def coverage_result(surface, root, capture, registration, geometry, at, registered_path=None):
    cloud = load_scan(root / capture.artifact.uri, AnalyticsConfig())
    # Use the unchanged estimated registration, never true pose.
    world = cloud.processing_world_m
    if registered_path is not None:
        with np.load(registered_path, allow_pickle=False) as data:
            world = data["points_m"].copy()
    bounds = []
    for p in geometry.patches:
        if p.status == "valid" and p.calibration_support >= 10 and p.asset_id == "BW-01":
            half = float(p.scale_m or 0.08) / np.sqrt(3)
            center = np.asarray(p.center_world_m)
            bounds.append([(center - half).tolist(), (center + half).tolist()])
    return surface.observed(
        "BW-01",
        world,
        capture.acquired_at,
        at,
        capture.capture_id,
        registration.status == "valid",
        geometry.status == "valid" and geometry.measurement_basis == "localized_relative",
        float(registration.uncertainty_score_m),
        bounds,
    )


def analyze(root, baseline, current, out, model, reference):
    return analyze_geometry(
        baseline,
        current,
        AnalyticsConfig(),
        reference,
        out,
        methods=["B3.1"],
        improved_calibration=model,
    )["B3.1"]


def run_e5(root, output, settings, smoke=False):
    if output.exists() and any(output.iterdir()):
        raise ValueError("E5 output must be new/empty")
    output.mkdir(parents=True, exist_ok=True)
    config = load_config(root / "configs/inspection/planner.yaml")
    surface = ReferenceSurface(root / config.reference_path, config.reference_sha256, config.cell_m)
    model = json.loads((root / "configs/fusion/calibration/geometry_b31.json").read_text())
    reference = load_reference(root / "configs/analytics/accepted_reference.json")
    policy = load_policy(root / "configs/fusion/hazards.yaml")
    freeze = {
        "configuration": config.model_dump(mode="json"),
        "configuration_hash": fingerprint(config),
        "settings": settings,
        "git": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "sources": {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ("inspection", "analytics", "fusion", "sensing")
            for p in sorted((root / "src/twinguard" / folder).glob("*.py"))
        },
        "partitions": {
            "development": settings["development_seeds"],
            "heldout": settings["heldout_seeds"],
        },
        "frozen_at_utc": __import__("datetime")
        .datetime.now(__import__("datetime").timezone.utc)
        .isoformat(),
    }
    if set(settings["development_seeds"]) & set(settings["heldout_seeds"]):
        raise ValueError("Partition overlap")
    save_json(output / "freeze.json", freeze)
    rows = []
    started = time.perf_counter()
    cases = list(SCENARIOS) if not smoke else ["E5-S03", "E5-S05", "E5-S10"]
    seeds = settings["development_seeds"][:1] if smoke else settings["heldout_seeds"]
    # E5-A uses same accepted map plus controlled policy constraints; small exact reference.
    base = PlanningSnapshot(
        snapshot_id="controlled",
        at=__import__("datetime").datetime(2025, 1, 1, tzinfo=__import__("datetime").timezone.utc),
        reference_hash=surface.hash,
        assets=[AssetPlanningState(asset_id="BW-01")],
    )
    pool = generate(surface, base, config, root)
    req = InspectionPlanningRequest(request_id="exact", method="P1", budget_views=2, budget_s=120)
    small = [v for v in pool if v.feasibility.status == "feasible" and v.modality == "lidar"][:6]
    greedy = plan(surface, base, config, req, small)
    exact = exact_coverage(surface, small, config, req)
    save_json(
        output / "E5-A.json",
        {
            "candidate_count": len(pool),
            "feasible": sum(v.feasibility.status == "feasible" for v in pool),
            "greedy_area_m2": greedy.expected_new_usable_area_m2,
            "exact": exact,
            "coverage_gap": exact["area_m2"] - greedy.expected_new_usable_area_m2,
            "scope": "Controlled geometry/software correctness; no fault detection claim",
        },
    )
    for sid in cases:
        for seed in seeds:
            case = f"{sid}-{seed}"
            trial = output / case
            trial.mkdir()
            kind = (
                "thermal"
                if sid == "E5-S08"
                else "geometric"
                if sid
                in ("E5-S03", "E5-S04", "E5-S05", "E5-S06", "E5-S07", "E5-S11", "E5-S15", "E5-S17")
                else "process"
                if sid in ("E5-S09", "E5-S10")
                else None
            )
            amplitude = [0.01, 0.02, 0.03, 0.05][seed % 4] if kind == "geometric" else 0
            scenario, faults = setup_scenario(root, case, seed, kind=kind, amplitude=amplitude)
            # Predeclared distribution, independent of planner. No favorable fault relocation.
            if kind == "geometric":
                rng = np.random.default_rng(seed)
                faults[0].center_local_m = (
                    float(rng.uniform(-0.25, 0.25)),
                    0,
                    float(rng.uniform(0.9, 1.5)),
                )
            if sid == "E5-S10":
                faults[0].true_process_deviation = 500000
            simulator = PlantSimulator(
                create_baseline_plant(load_plant_config(root / "configs/plant.yaml"), seed),
                scenario,
                faults,
            )
            installation = load_installation(
                root
                / (
                    "configs/sensing/L2.yaml"
                    if sid in ("E5-S05", "E5-S15")
                    else "configs/sensing/L1.yaml"
                )
            )
            scenario.inspections = [
                InspectionSchedule(
                    sensor_id=installation.lidar.sensor_id, offset_s=t, modality="lidar"
                )
                for t in (0, 60)
            ]
            if sid == "E5-S08":
                scenario.inspections += [
                    InspectionSchedule(
                        sensor_id=installation.thermal.sensor_id, offset_s=t, modality="thermal"
                    )
                    for t in (0, 60)
                ]
            scenario.sensor_config_ids = [installation.lidar.sensor_id] + (
                [installation.thermal.sensor_id] if sid == "E5-S08" else []
            )
            if sid in ("E5-S09", "E5-S10"):
                scenario.sensor_config_ids.append("pressure-01")
            initial = trial / "initial"
            initial_install = installation.model_copy(deep=True)
            if sid in ("E5-S04", "E5-S06"):
                initial_install.lidar.horizontal_fov_rad = 0.25
                initial_install.event_poses = {}
            acquire(simulator.sensing_reader(), scenario, initial_install, initial, modality="all")
            captures = [
                r for r in load_public_observations(initial) if isinstance(r, InspectionCapture)
            ]
            lidar = sorted(
                [r for r in captures if r.modality == "lidar"], key=lambda r: r.acquired_at
            )
            registration, geometry = analyze(
                root,
                initial / lidar[0].artifact.uri,
                initial / lidar[-1].artifact.uri,
                trial / "initial-analysis",
                model,
                reference,
            )
            at = lidar[-1].acquired_at + timedelta(seconds=1)
            evidence = adapters.geometry(
                geometry, registration, processing(geometry, at), lidar[-1].provenance_id
            )
            if sid == "E5-S08":
                for capture in [r for r in captures if r.modality == "thermal"]:
                    result, _ = infer_thermal(
                        initial,
                        capture,
                        root / "configs/fusion/calibration",
                        AnalyticsConfig(),
                        reference,
                        method="conditioned",
                    )
                    evidence.extend(
                        adapters.thermal(result, processing(result, at), capture.provenance_id)
                    )
            if sid in ("E5-S09", "E5-S10"):
                from twinguard.core.contracts import SensorObservation
                from twinguard.analytics.operating import infer_operating

                observations = [
                    o
                    for o in load_public_observations(initial)
                    if isinstance(o, SensorObservation) and o.acquired_at <= at
                ]
                pressure = max(
                    (
                        o
                        for o in observations
                        if o.sensor_id == "pressure-01" and o.quality == "good"
                    ),
                    key=lambda o: o.acquired_at,
                )
                arrival = max(at, pressure.received_at)
                proc = ProcessingRecord(
                    source_id=pressure.observation_id,
                    received_at=arrival,
                    processed_at=arrival,
                    available_at=arrival,
                    basis="simulated_replay",
                    rationale="Actual synthetic measured pressure, explicit replay clock",
                    clock_quality="synchronized",
                )
                evidence.append(adapters.engineering_limit(pressure, proc, policy))
                opmodel = json.loads(
                    (root / "configs/fusion/calibration/operating_model.json").read_text()
                )
                predictions = infer_operating(observations, opmodel, AnalyticsConfig())
                prediction = next(
                    (v for v in predictions if v.observation_id == pressure.observation_id), None
                )
                if prediction:
                    proc.source_id = prediction.prediction_id
                    evidence.append(adapters.operating(prediction, pressure, proc))
                at = arrival
            state, traces = assess(FusionState(), evidence, policy, at)
            conditions = {t.assessment.asset_id: t.model_dump(mode="json") for t in traces}
            states = public_states(
                at,
                sorted(set(surface.assets)),
                conditions,
                [e.model_dump(mode="json") for e in state.events.values()],
            )
            cov = coverage_result(
                surface,
                initial,
                lidar[-1],
                registration,
                geometry,
                at,
                trial / "initial-analysis/B3.1/registered_current.npz",
            )
            snap = PlanningSnapshot(
                snapshot_id="snapshot-" + case,
                at=at,
                reference_hash=surface.hash,
                assets=states,
                coverage=[cov],
                input_refs=[
                    geometry.analysis_id,
                    registration.registration_id,
                    lidar[-1].capture_id,
                ],
            )
            c = config.model_copy(deep=True)
            if sid in ("E5-S05", "E5-S15"):
                c.sensor_path = "configs/sensing/L2.yaml"
            if sid == "E5-S02":
                for item in snap.coverage:
                    item.acquired_at -= timedelta(seconds=7200)
                    item.available_at -= timedelta(seconds=7200)
            if sid == "E5-S10":
                c.restricted_assets = ["BW-01"]
            if sid == "E5-S12":
                c.no_go = [Box(lower=c.allowed_volume.lower, upper=c.allowed_volume.upper)]
            if sid == "E5-S13":
                c.minimum_registration_returns = 100000
            if sid == "E5-S14":
                c.calibrated_range_m = (6, 7)
            if sid == "E5-S16":
                c.criticality = {}
                snap.coverage = []
            if sid == "E5-S18":
                c.no_go = [Box(lower=(-0.3, 1, 0.4), upper=(0.3, 3, 4))]
            save_json(trial / "initial-snapshot.json", snap)
            save_json(trial / "config.json", c)
            candidates = generate(surface, snap, c, root)
            # Same complete candidate pool and budgets for all methods.
            save_json(trial / "candidates.json", [v.model_dump(mode="json") for v in candidates])
            for method in ("P0", "P1", "P2", "P3"):
                work = trial / method
                work.mkdir()
                current = snap.model_copy(deep=True)
                fstate = copy.deepcopy(state)
                request = InspectionPlanningRequest(
                    request_id=f"{case}-{method}",
                    method=method,
                    budget_views=1 if sid == "E5-S17" else 2,
                    budget_s=20 if sid == "E5-S17" else 70,
                )
                frozen = plan(surface, current, c, request, candidates)
                save_json(work / "plan.json", frozen)
                seal_predictions(
                    work,
                    {"policy": fingerprint(c), "method": method},
                    [
                        fingerprint(snap),
                        fingerprint([v.model_dump(mode="json") for v in candidates]),
                    ],
                )
                initial_qualified = set(cov.qualified_cells)
                observed = set(cov.observed_cells)
                qualified = set(initial_qualified)
                useful = False
                registrations = []
                patches = []
                failures = 0
                volume = 0
                results = []
                cost_s = 0.0
                travel_m = 0.0
                before = time.perf_counter()
                selected = list(frozen.steps[:1] if method == "P3" else frozen.steps)
                actual_position = np.asarray(c.start_world_m, float)
                executed_steps = []
                for index, step in enumerate(selected):
                    chosen = next(
                        v for v in frozen.candidates if v.viewpoint_id == step.viewpoint_id
                    )
                    target = np.asarray(chosen.planned_pose.matrix)[:3, 3]
                    actual_travel = float(np.linalg.norm(target - actual_position))
                    home = (
                        float(np.linalg.norm(target - c.start_world_m)) if c.return_to_start else 0
                    )
                    from twinguard.inspection.feasibility import route

                    if (
                        not route(surface, actual_position, target, c)
                        or cost_s
                        + actual_travel / c.speed_m_s
                        + chosen.acquisition_s
                        + home / c.speed_m_s
                        > request.budget_s
                        or travel_m + actual_travel + home > request.maximum_travel_m
                    ):
                        break
                    step = step.model_copy(
                        update={"travel_m": actual_travel, "travel_s": actual_travel / c.speed_m_s}
                    )
                    executed_steps.append(step)
                    acq = work / f"view-{index}"
                    inst = installation.model_copy(deep=True)
                    inst.event_poses = {}
                    sensor = inst.lidar if chosen.modality == "lidar" else inst.thermal
                    sensor.pose = chosen.planned_pose
                    sensor.asset_id = chosen.asset_id
                    # Requested pose is passed only after plan seal. Actual remains controller-private; sensor reports noisy pose.
                    acquire(
                        simulator.sensing_reader(),
                        scenario,
                        inst,
                        acq,
                        modality=chosen.modality,
                        time_s=62 + index * 8,
                    )
                    capture = next(
                        r for r in load_public_observations(acq) if isinstance(r, InspectionCapture)
                    )
                    available = max(current.at, capture.acquired_at) + timedelta(seconds=1)
                    if chosen.modality == "lidar":
                        r, g = analyze(
                            root,
                            initial / lidar[0].artifact.uri,
                            acq / capture.artifact.uri,
                            work / f"analysis-{index}",
                            model,
                            reference,
                        )
                        ev = adapters.geometry(
                            g, r, processing(g, available), capture.provenance_id
                        )
                        coverage = coverage_result(
                            surface,
                            acq,
                            capture,
                            r,
                            g,
                            available,
                            work / f"analysis-{index}/B3.1/registered_current.npz",
                        )
                        observed.update(coverage.observed_cells)
                        qualified.update(coverage.qualified_cells)
                        registrations.append(r.status == "valid")
                        patches.append(
                            sum(
                                p.status == "valid" and p.calibration_support >= 10
                                for p in g.patches
                            )
                        )
                        failures += g.status != "valid"
                        useful = useful or any(e.finding == "positive" for e in ev)
                        results.append(
                            {
                                "analysis": g.model_dump(mode="json"),
                                "registration": r.model_dump(mode="json"),
                                "coverage": coverage.model_dump(mode="json"),
                                "viewpoint_id": chosen.viewpoint_id,
                            }
                        )
                        current.coverage.append(coverage)
                    else:
                        t, _ = infer_thermal(
                            acq,
                            capture,
                            root / "configs/fusion/calibration",
                            AnalyticsConfig(),
                            reference,
                            method="conditioned",
                        )
                        ev = adapters.thermal(t, processing(t, available), capture.provenance_id)
                        failures += t.status != "valid"
                        results.append(
                            {
                                "thermal": t.model_dump(mode="json"),
                                "viewpoint_id": chosen.viewpoint_id,
                            }
                        )
                    fstate, newtraces = assess(fstate, ev, policy, available)
                    current.at = available
                    current.previous_plan_id = frozen.plan_id
                    current.attempted_viewpoints.append(chosen.viewpoint_id)
                    current.assets = public_states(
                        available,
                        sorted(set(surface.assets)),
                        {t.assessment.asset_id: t.model_dump(mode="json") for t in newtraces},
                        [e.model_dump(mode="json") for e in fstate.events.values()],
                    )
                    for a in current.assets:
                        if a.asset_id == chosen.asset_id:
                            a.unsuccessful_attempts += int(failures > 0)
                    save_json(work / f"snapshot-{index}.json", current)
                    cost_s += step.travel_s + step.acquisition_s
                    travel_m += step.travel_m
                    actual_position = target
                    remaining_s = request.budget_s - cost_s
                    nextrequest = request.model_copy(
                        update={
                            "budget_views": max(1, request.budget_views - index - 1),
                            "budget_s": max(0.001, remaining_s),
                        }
                    )
                    nextplan = plan(surface, current, c, nextrequest, candidates)
                    save_json(work / f"replan-{index}.json", nextplan)
                    seal_predictions(
                        work / f"replan-seal-{index}",
                        {"plan_hash": fingerprint(nextplan)},
                        [fingerprint(current)],
                    )
                    if method == "P3" and index + 1 < request.budget_views and nextplan.steps:
                        selected.append(nextplan.steps[0])
                    volume += sum(
                        p.stat().st_size
                        for p in acq.rglob("*")
                        if p.is_file() and "evaluation_private" not in p.parts
                    )
                if executed_steps and c.return_to_start:
                    home = float(np.linalg.norm(actual_position - c.start_world_m))
                    travel_m += home
                    cost_s += home / c.speed_m_s
                save_json(
                    work / "executed-steps.json",
                    [v.model_dump(mode="json") for v in executed_steps],
                )
                save_json(work / "results.json", results)
                save_json(work / "F1.json", fstate)
                seal_predictions(
                    work, {"policy": fingerprint(c), "method": method}, [fingerprint(snap)]
                )
                # Only evaluator below reads labels after public plans/results seal.
                from .analytics import verify_seal

                verify_seal(work)
                truth = simulator.ground_truth_at(60, case).model_dump(mode="json")
                save_json(trial / "evaluation_private" / "truth.json", truth)
                # Require region overlap with the held-out true footprint; unrelated positives cannot count.
                detected = False
                if kind == "geometric":
                    fault = faults[0]
                    center = np.asarray(fault.center_local_m) + [0, 0, 0.35]
                    extent = np.asarray(fault.extent_m)
                    for result in results:
                        for region in result.get("analysis", {}).get("regions", []):
                            lo, hi = np.asarray(region["bounds_world_m"])
                            if (
                                np.all(hi >= center - extent)
                                and np.all(lo <= center + extent)
                                and result["analysis"]["status"] == "valid"
                            ):
                                detected = True
                area = float(surface.area[surface.assets == "BW-01"].sum())
                actual_new = surface.area_of(observed - set(cov.observed_cells))
                row = {
                    "scenario": sid,
                    "seed": seed,
                    "method": method,
                    "partition": "development" if smoke else "heldout",
                    "amplitude_m": amplitude,
                    "geometric_positive": kind == "geometric",
                    "detected": detected,
                    "positive_evidence": useful,
                    "plan_hash": fingerprint(frozen),
                    "snapshot_hash": fingerprint(snap),
                    "candidate_hash": fingerprint([v.model_dump(mode="json") for v in candidates]),
                    "budget_s": request.budget_s,
                    "budget_views": request.budget_views,
                    "views": len(executed_steps),
                    "plan_status": frozen.status,
                    "predicted_new_area_m2": frozen.expected_new_usable_area_m2,
                    "actual_new_area_m2": actual_new,
                    "qualified_new_area_m2": surface.area_of(qualified - initial_qualified),
                    "qualified_fraction": surface.area_of(qualified) / area,
                    "prediction_error_m2": actual_new - frozen.expected_new_usable_area_m2,
                    "registration_success": sum(registrations),
                    "registrations": len(registrations),
                    "qualified_patches": sum(patches),
                    "inconclusive_acquisitions": failures,
                    "estimated_duration_s": cost_s,
                    "estimated_travel_m": travel_m,
                    "processing_wall_s": time.perf_counter() - before,
                    "planning_runtime_s": frozen.optimization_runtime_s,
                    "data_bytes": volume,
                    "unresolved_after_budget": len(qualified) == 0,
                    "critical_review_omitted": False,
                    "limitations": [
                        "Mission time is static simulation proxy",
                        "Pressure scenarios use original imperfect virtual IoT observations and existing engineering-limit/F1 adapters",
                        "P3 executes frozen causal replans within remaining original budget; other methods execute frozen sequence",
                    ],
                }
                rows.append(row)
            save_json(
                output / "progress.json",
                {
                    "completed_trials": len(rows) // 4,
                    "method_runs": len(rows),
                    "last": case,
                    "elapsed_s": time.perf_counter() - started,
                },
            )
            print(case, "done", len(rows), flush=True)
    save_json(output / "trial_table.json", rows)
    summary = {}
    for method in ("P0", "P1", "P2", "P3"):
        group = [r for r in rows if r["method"] == method]
        positive = [r for r in group if r["geometric_positive"]]
        summary[method] = {
            "runs": len(group),
            "views": sum(r["views"] for r in group),
            "detected": sum(r["detected"] for r in positive),
            "positive_trials": len(positive),
            "actual_new_area_mean_m2": float(np.mean([r["actual_new_area_m2"] for r in group])),
            "qualified_new_area_mean_m2": float(
                np.mean([r["qualified_new_area_m2"] for r in group])
            ),
            "planning_runtime_mean_s": float(np.mean([r["planning_runtime_s"] for r in group])),
            "inconclusive_acquisitions": sum(r["inconclusive_acquisitions"] for r in group),
            "by_amplitude": {
                str(mm): {
                    "detected": sum(
                        r["detected"] for r in positive if round(r["amplitude_m"] * 1000) == mm
                    ),
                    "trials": sum(round(r["amplitude_m"] * 1000) == mm for r in positive),
                }
                for mm in (10, 20, 30, 50)
            },
        }
    report = {
        "experiment_id": "E5",
        "status": "executed",
        "heldout_independent_seeds": len(seeds),
        "scenario_classes": len(cases),
        "trial_count": len(rows) // 4,
        "method_runs": len(rows),
        "elapsed_s": time.perf_counter() - started,
        "summary": summary,
        "limitations": [
            "P3 causal adaptive execution; ablations use separate runs when executed",
            "No hardware flight or sensor validation",
            "Live fast-worker load assessed separately",
        ],
    }
    save_json(output / "report.json", report)
    report_figures(output)
    return report


def report_figures(output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = json.loads((output / "trial_table.json").read_text())
    figures = output / "figures"
    figures.mkdir(exist_ok=True)
    methods = ["P0", "P1", "P2", "P3"]
    for number, title, key in [
        (2, "Measured new reference area", "actual_new_area_m2"),
        (5, "Predicted versus measured area error", "prediction_error_m2"),
        (7, "Actual qualified localized detections", "detected"),
        (8, "Estimated mission duration (simulation proxy)", "estimated_duration_s"),
        (9, "Inconclusive acquisitions incl. L2", "inconclusive_acquisitions"),
    ]:
        fig, ax = plt.subplots(figsize=(8, 4))
        values = [np.mean([r[key] for r in rows if r["method"] == m]) for m in methods]
        ax.bar(methods, values, color=["#64748b", "#22b8b0", "#de9e36", "#8469ce"])
        ax.set_title(title)
        ax.set_ylabel("Mean per trial")
        fig.tight_layout()
        fig.savefig(figures / f"E5-{number}.png", dpi=160)
        plt.close(fig)
    return figures
