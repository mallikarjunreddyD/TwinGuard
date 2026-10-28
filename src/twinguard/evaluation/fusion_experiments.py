"""Privileged E3 controller; production fusion receives public evidence only."""

from pathlib import Path
from datetime import timedelta
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import get_context
import hashlib
import json
import time
import resource
import subprocess
from twinguard.fusion.policies import load_policy, policy_hash
from twinguard.fusion.models import ProcessingRecord, FusionState
from twinguard.fusion import adapters
from twinguard.fusion.engine import replay, assess
from twinguard.fusion.io import save, save_evidence, write_run
from twinguard.core.contracts import InspectionSchedule, InspectionCapture
from twinguard.core.analytics_contracts import GeometryResult, RegistrationResult
from twinguard.core.observations import load_public_observations
from twinguard.analytics.config import AnalyticsConfig
from twinguard.analytics.reference import load_reference
from twinguard.analytics.pipeline import analyze_geometry
from twinguard.analytics.operating import infer_operating, measured_records
from twinguard.analytics.thermal import infer_thermal
from twinguard.plant.config import load_plant_config
from twinguard.plant.model import create_baseline_plant
from twinguard.plant.simulator import PlantSimulator
from twinguard.sensing.acquisition import acquire, load_installation
from .experiments import setup_scenario
from .sensing import attach_plant_truth
from .analytics import verify_seal
from .fusion_scenarios import START, controlled
from .fusion_metrics import evaluate_case, summarize

CONDITIONS = [
    "healthy",
    "normal_load",
    "geometry",
    "thermal",
    "pressure",
    "critical_pressure",
    "temperature",
    "geometry_only",
    "pressure_no_uav",
    "stale_inspection",
    "L2_geometry",
    "missing_duplicate",
    "image_only_context",
    "uncalibrated_critical_pressure",
    "spatial_mismatch",
]


def simulated_processing(source, received, delay):
    available = received + timedelta(seconds=delay)
    return ProcessingRecord(
        source_id=source,
        received_at=received,
        processed_at=available,
        available_at=available,
        basis="simulated_replay",
        clock_quality="synchronized",
        rationale="Versioned E3 simulation: 0.05s raw ingestion, 0.25s operating/thermal processing; measured geometry runtime. Not original offline availability or measured service latency.",
    )


def schedule(records, policy, at, method, step=5):
    state = FusionState()
    history = []
    ordered = sorted(records, key=lambda e: (e.available_at, e.evidence_id))
    cursor = 0
    # A periodic simulated acquisition-time horizon; no result arrives before its declared availability.
    begin = at - timedelta(seconds=125)
    for tick in range(0, 126, step):
        timestamp = begin + timedelta(seconds=tick)
        incoming = []
        while cursor < len(ordered) and ordered[cursor].available_at <= timestamp:
            incoming.append(ordered[cursor])
            cursor += 1
        state, decisions = assess(state, incoming, policy, timestamp, method=method)
        history.extend(decisions)
    return state, history


def run_controlled(root, output, config):
    rows = []
    policy = load_policy(root / config["policy"])
    for seed in config["controlled_seeds"]:
        for case in range(1, 23):
            case_id = f"case-{len(rows) // 2:05d}"
            directory = output / "controlled" / case_id
            evidence, actions, case_policy, at, label = controlled(case, seed, policy)
            save_evidence(
                directory / "inputs",
                evidence,
                {"kind": "controlled policy semantics", "seed": seed},
            )
            # Predictions saved/sealed before the label is opened by the evaluator.
            for method in ["F0", "F1"]:
                state, history = replay(evidence, case_policy, at, actions, method=method)
                prediction = directory / method
                write_run(
                    prediction,
                    state,
                    history,
                    case_policy,
                    {"track": "controlled", "seed": seed, "case_id": case_id},
                )
            restricted = directory / "evaluation_private"
            restricted.mkdir(mode=0o700)
            label.update(
                event_positive=case in [2, 3, 4, 5, 6, 7, 8, 9, 10, 13, 17, 18, 19, 20],
                onset=(
                    START + timedelta(seconds=1)
                    if case in [2, 3, 4, 5, 6, 7, 8, 9, 10, 13, 17, 18, 19, 20]
                    else START - timedelta(seconds=1)
                ).isoformat(),
                end=at.isoformat(),
            )
            label["expected_hypotheses"] = (
                ["localized_geometric_change"]
                if case in [2, 9]
                else ["abnormal_thermal_residual"]
                if case == 3
                else ["abnormal_process_pressure_residual"]
                if case in [4, 10]
                else ["localized_geometric_change", "abnormal_thermal_residual"]
                if case == 8
                else ["critical_pressure_limit"]
            )
            save(restricted / "label.json", label)
            (restricted / "label.json").chmod(0o600)
            for method in ["F0", "F1"]:
                values = evaluate_case(directory / method, label)
                rows.append(
                    {
                        "track": "controlled",
                        "condition": f"E3-C{case:02d}",
                        "case_id": case_id,
                        "seed": seed,
                        "method": method,
                        **values,
                    }
                )
    save(output / "controlled_results.json", {"rows": rows, "metrics": summarize(rows)})
    return rows


def end_to_end_worker(arguments):
    root_string, output_string, case_id, seed, condition, config = arguments
    root = Path(root_string)
    directory = Path(output_string) / "end_to_end" / case_id
    policy = load_policy(root / config["policy"])
    algorithm = AnalyticsConfig()
    reference = load_reference(root / "configs/analytics/accepted_reference.json")
    scenario, faults = setup_scenario(
        root,
        case_id,
        seed,
        profile="increase"
        if condition == "normal_load"
        else "mismatch"
        if condition == "uncalibrated_critical_pressure"
        else "steady",
        kind="geometric"
        if condition in ["geometry", "geometry_only", "L2_geometry", "image_only_context"]
        else "thermal"
        if condition == "thermal"
        else "process"
        if condition
        in [
            "pressure",
            "critical_pressure",
            "pressure_no_uav",
            "temperature",
            "uncalibrated_critical_pressure",
            "spatial_mismatch",
        ]
        else None,
        amplitude=0.02,
    )
    shift = timedelta(days=2)
    scenario.simulation_start += shift
    faults = [
        f.model_copy(update={"start_at": f.start_at + shift, "end_at": f.end_at + shift})
        for f in faults
    ]
    if condition in ["critical_pressure", "pressure_no_uav", "uncalibrated_critical_pressure"]:
        faults[0].true_process_deviation = 500000
    if condition in ["temperature", "spatial_mismatch"]:
        faults[0].process_variable = "temperature_c"
        faults[0].deviation_unit = "degC"
        faults[0].true_process_deviation = 70
    if condition == "spatial_mismatch":
        _, extra_geometry = setup_scenario(
            root, case_id + "-structure", seed, kind="geometric", amplitude=0.02
        )
        faults.extend(
            [
                f.model_copy(update={"start_at": f.start_at + shift, "end_at": f.end_at + shift})
                for f in extra_geometry
            ]
        )
    if condition == "image_only_context":
        _, extra = setup_scenario(root, case_id + "-extra", seed, kind="thermal")
        faults.extend(
            [
                f.model_copy(update={"start_at": f.start_at + shift, "end_at": f.end_at + shift})
                for f in extra
            ]
        )
    scenario.fault_config_references = [f.fault_id for f in faults]
    installation = load_installation(
        root
        / ("configs/sensing/L2.yaml" if condition == "L2_geometry" else "configs/sensing/L1.yaml")
    )
    scenario.sensor_config_ids = [installation.lidar.sensor_id, installation.thermal.sensor_id] + [
        s.sensor_id for s in installation.iot
    ]
    scenario.inspections = [
        InspectionSchedule(sensor_id=installation.lidar.sensor_id, offset_s=t, modality="lidar")
        for t in [0, 60]
    ] + [
        InspectionSchedule(sensor_id=installation.thermal.sensor_id, offset_s=t, modality="thermal")
        for t in [0, 30, 60, 90, 120]
    ]
    simulator = PlantSimulator(
        create_baseline_plant(load_plant_config(root / "configs/plant.yaml"), seed),
        scenario,
        faults,
    )
    data = directory / "public-data"
    acquire(simulator.sensing_reader(), scenario, installation, data)
    attach_plant_truth(data, simulator)
    records = load_public_observations(data)
    captures = [r for r in records if isinstance(r, InspectionCapture)]
    iot = measured_records(data)
    op_model = json.loads((root / config["operating_model"]).read_text())
    thermal_model = root / config["thermal_model_directory"]
    geometric_calibration = json.loads((root / config["geometric_calibration"]).read_text())
    old_calibration = json.loads((root / config["original_geometry_calibration"]).read_text())
    lidar = sorted([r for r in captures if r.modality == "lidar"], key=lambda r: r.acquired_at)
    geometric_output = directory / "analytics-geometry"
    results = analyze_geometry(
        data / lidar[0].artifact.uri,
        data / lidar[1].artifact.uri,
        algorithm,
        reference,
        geometric_output,
        old_calibration,
        methods=["B3", "B3.1"],
        improved_calibration=geometric_calibration,
    )
    registration, geometry = results["B3.1"]
    fusion_evidence = adapters.geometry(
        geometry,
        registration,
        simulated_processing(
            geometry.analysis_id, lidar[1].received_at, registration.runtime_s + geometry.runtime_s
        ),
        lidar[1].provenance_id,
    )
    old_registration, old_geometry = results["B3"]
    alternative = adapters.geometry(
        old_geometry,
        old_registration,
        simulated_processing(
            old_geometry.analysis_id,
            lidar[1].received_at,
            old_registration.runtime_s + old_geometry.runtime_s,
        ),
        lidar[1].provenance_id,
    )
    fusion_evidence += alternative
    if condition == "stale_inspection":
        # Legitimate old public observation/result, not a retimed current scan.
        old = root / config["historical_geometry"]
        g = GeometryResult.model_validate_json((old / "geometry.json").read_text())
        r = RegistrationResult.model_validate_json((old / "registration.json").read_text())
        fusion_evidence = adapters.geometry(
            g,
            r,
            simulated_processing(
                g.analysis_id, g.acquired_at + timedelta(seconds=0.1), g.runtime_s + r.runtime_s
            ),
            json.loads((old.parent / "provenance.json").read_text())["provenance_id"],
        )
    by_observation = {r.observation_id: r for r in iot}
    operating = infer_operating(iot, op_model, algorithm, "conditioned_quality")
    save(directory / "analytics-operating.json", [p.model_dump(mode="json") for p in operating])
    for p in operating:
        source = by_observation[p.observation_id]
        if source.sensor_id not in [
            "pressure-01",
            "temperature-01",
            "wall-thermometer",
            "pipe-temperature",
        ]:
            continue
        fusion_evidence.append(
            adapters.operating(
                p,
                source,
                simulated_processing(
                    p.prediction_id, max(source.received_at, p.available_at), 0.25
                ),
            )
        )
    thermal_outputs = []
    for capture in [r for r in captures if r.modality == "thermal"]:
        t, _ = infer_thermal(data, capture, thermal_model, algorithm)
        thermal_outputs.append(t.model_dump(mode="json"))
        fusion_evidence.extend(
            adapters.thermal(
                t,
                simulated_processing(t.analysis_id, capture.received_at, 0.25),
                capture.provenance_id,
            )
        )
    save(directory / "analytics-thermal.json", thermal_outputs)
    for source in iot:
        if source.sensor_id not in ["pressure-01", "temperature-01"]:
            continue
        value = adapters.engineering_limit(
            source, simulated_processing(source.observation_id, source.received_at, 0.05), policy
        )
        if value:
            fusion_evidence.append(value)
    if condition == "geometry_only":
        fusion_evidence = [e for e in fusion_evidence if e.modality == "geometric"]
    if condition == "pressure_no_uav":
        fusion_evidence = [e for e in fusion_evidence if e.modality == "fixed_sensor"]
    if condition == "missing_duplicate":
        fusion_evidence = [e for e in fusion_evidence if e.sensor_id != "pressure-01"]
        fusion_evidence += fusion_evidence[:6]
    if condition == "spatial_mismatch":
        fusion_evidence = [
            e
            for e in fusion_evidence
            if e.modality == "geometric" or e.sensor_id in ["pipe-temperature", "pressure-01"]
        ]
    save_evidence(
        directory / "inputs",
        fusion_evidence,
        {
            "source_manifest": str(data / "manifest.json"),
            "acquisition_profile": installation.fidelity,
            "delivery_profile": {
                "geometry_only": "inspection_only",
                "pressure_no_uav": "fixed_stream_only",
                "missing_duplicate": "missing_pressure_channel_retransmission",
            }.get(condition, "nominal"),
            "availability_contract": "E3 simulated processing v1",
        },
    )
    timings = {}
    for method in ["F0", "F1"]:
        started = time.perf_counter()
        state, history = schedule(
            fusion_evidence,
            policy,
            scenario.simulation_start + timedelta(seconds=125),
            method,
            config["assessment_step_s"],
        )
        timings[method] = time.perf_counter() - started
        write_run(
            directory / method,
            state,
            history,
            policy,
            {
                "track": "end_to_end",
                "input_manifest": str(directory / "inputs/manifest.json"),
                "processing_runtime_s": timings[method],
                "simulated_assessment_step_s": config["assessment_step_s"],
            },
        )
    # All restricted evaluation starts after both methods' predictions are persisted and sealed.
    for method in ["F0", "F1"]:
        verify_seal(directory / method)
    context = json.loads((data / "evaluation_private/plant_truth.json").read_text())
    truth = context["ground_truth_snapshots"][-1]["fault_states"]
    positive = bool(truth)
    target = "inspection-context" if condition == "thermal" else "BW-01"
    actual = simulator.operating_at(60)
    pressure_limit = next(
        a.critical_limit for a in policy.authorities if a.sensor_id == "pressure-01"
    )
    temperature_limit = next(
        a.critical_limit for a in policy.authorities if a.sensor_id == "temperature-01"
    )
    critical = bool(
        positive
        and (
            actual.process_pressure_pa >= pressure_limit
            or actual.process_temperature_c >= temperature_limit
        )
    )
    label = {
        "track": "end_to_end",
        "event_positive": positive,
        "critical_event": critical,
        "target_asset": target,
        "onset": (
            scenario.simulation_start + timedelta(seconds=30)
            if positive
            else scenario.simulation_start
        ).isoformat(),
        "end": (scenario.simulation_start + timedelta(seconds=125)).isoformat(),
        "condition": condition,
        "label_basis": "Restricted physical fault configuration after saved predictions; critical label compares actual private process values to explicitly illustrative configured limits; thermal evaluated at inspection context only",
    }
    label["expected_hypotheses"] = (
        ["critical_pressure_limit"]
        if critical and actual.process_pressure_pa >= pressure_limit
        else ["critical_temperature_limit"]
        if critical
        else ["abnormal_process_pressure_residual"]
        if condition == "pressure"
        else ["abnormal_thermal_residual"]
        if condition == "thermal"
        else ["localized_geometric_change"]
    )
    geometric_fault = next(
        (f["configuration"] for f in truth if f["category"] == "localized_geometric_deformation"),
        None,
    )
    if geometric_fault and not critical:
        localized = []
        for e in fusion_evidence:
            if e.modality != "geometric" or e.finding != "positive" or e.bounds_world_m is None:
                continue
            center = [(a + b) / 2 for a, b in zip(*e.bounds_world_m)]
            radius = (
                (center[0] - geometric_fault["center_local_m"][0]) / geometric_fault["extent_m"][0]
            ) ** 2 + (
                (center[2] - 0.35 - geometric_fault["center_local_m"][2])
                / geometric_fault["extent_m"][2]
            ) ** 2
            if radius <= 1:
                localized.append(e.evidence_id)
        label["localized_evidence_ids"] = localized
    private = directory / "evaluation_private"
    private.mkdir(mode=0o700)
    save(private / "label.json", label)
    (private / "label.json").chmod(0o600)
    rows = [
        {
            "track": "end_to_end",
            "condition": condition,
            "case_id": case_id,
            "seed": seed,
            "method": method,
            "fusion_runtime_s": timings[method],
            **evaluate_case(directory / method, label),
        }
        for method in ["F0", "F1"]
    ]
    save(private / "metrics.json", rows)
    return rows, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def run_e3(root, output, config, smoke=False):
    if output.exists() and any(output.iterdir()):
        raise ValueError("E3 output must be empty")
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    policy = load_policy(root / config["policy"])
    if set(config["controlled_seeds"]) & set(config["end_to_end_seeds"]):
        raise ValueError("E3 partitions overlap")
    if smoke:
        config = {
            **config,
            "controlled_seeds": config["development_controlled_seeds"],
            "end_to_end_seeds": config["development_end_to_end_seeds"],
        }
    frozen = policy_hash(policy)
    save(output / "configuration.json", config)
    save(output / "policy.json", policy)
    source_hashes = {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((root / "src/twinguard/fusion").glob("*.py"))
    }
    a = run_controlled(root, output, config)
    jobs = []
    for seed in config["end_to_end_seeds"]:
        for condition in CONDITIONS:
            jobs.append((str(root), str(output), f"case-{len(jobs):05d}", seed, condition, config))
    b = []
    peak = 0
    with ProcessPoolExecutor(
        max_workers=config["workers"], mp_context=get_context("spawn")
    ) as pool:
        futures = [pool.submit(end_to_end_worker, j) for j in jobs]
        for future in as_completed(futures):
            rows, rss = future.result()
            b += rows
            peak = max(peak, rss)
            if len(b) % 20 == 0:
                print("E3-B completed", len(b) // 2, "/", len(jobs), flush=True)
    assert policy_hash(policy) == frozen
    assert all(
        hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
        for name, digest in source_hashes.items()
    )
    report = {
        "experiment_id": "E3",
        "configuration": config,
        "policy_sha256": frozen,
        "source_sha256": source_hashes,
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "software_version": __import__("twinguard").__version__,
        "controlled": {"cases": len(a) // 2, "metrics": summarize(a), "rows": a},
        "end_to_end": {
            "cases": len(b) // 2,
            "metrics": summarize(b),
            "rows": sorted(b, key=lambda r: (r["case_id"], r["method"])),
        },
        "runtime_s": time.perf_counter() - started,
        "max_worker_rss_mib": peak,
        "parent_peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        "smoke": smoke,
    }
    save(output / "report.json", report)
    return report
