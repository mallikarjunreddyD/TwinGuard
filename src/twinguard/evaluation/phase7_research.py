"""Phase 7 independent controller/evaluator. Never imported by analytics or planning."""

from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import json
import time
import hashlib
import resource
import numpy as np
from twinguard.analytics.config import AnalyticsConfig
from twinguard.analytics.reference import load_reference
from twinguard.analytics.pipeline import analyze_geometry
from twinguard.core.contracts import InspectionCapture
from twinguard.core.observations import load_public_observations
from twinguard.core.spatial import Transform
from .viewpoint_campaign import acquire_pair, standard_poses
from .campaigns import Campaign, atomic_json, resource_preflight
from .analytics import verify_seal


def region_matches(geometry, fault):
    if geometry.status != "valid":
        return []
    patches = {p.patch_id: p for p in geometry.patches}
    matched = []
    for region in geometry.regions:
        yes = False
        if (
            fault
            and region.asset_id == fault["asset_id"]
            and region.association_status == "associated"
        ):
            center = np.asarray(fault["configuration"]["center_local_m"]) + [0, 0, 0.35]
            extent = np.asarray(fault["configuration"]["extent_m"])
            for ident in region.patch_ids:
                p = patches.get(ident)
                if (
                    p
                    and p.status == "valid"
                    and p.significant is True
                    and p.calibration_support >= 10
                    and sum(((p.center_world_m[j] - center[j]) / extent[j]) ** 2 for j in (0, 2))
                    <= 1
                ):
                    yes = True
        matched.append(yes)
    return matched


def detector_case(task):
    root, output, case_id, seed, level, pose_name, pose_json, amplitude, operating, partition = task
    root = Path(root)
    output = Path(output)
    resource_preflight(reserve_bytes=20 * 1024**2)
    done = output / "completed_units" / f"{case_id}.json"
    if done.exists():
        return json.loads(done.read_text())
    data = output / "datasets" / case_id
    if not (data / "manifest.json").exists():
        if data.exists():
            # Preserve interrupted raw fragments; never overwrite a prior acquisition.
            data = data.with_name(case_id + "-attempt-" + str(time.time_ns()))
        pose = Transform.model_validate(pose_json)
        rng = np.random.default_rng(seed + int(amplitude * 1e6))
        matrix = np.asarray(pose.matrix)
        matrix[:3, 3] += rng.uniform(-0.035, 0.035, 3)
        pose = pose.model_copy(update={"matrix": matrix.tolist()})
        baseline = standard_poses(root)["reference"].model_copy(deep=True)
        matrix = np.asarray(baseline.matrix)
        matrix[:3, 3] += rng.uniform(-0.025, 0.025, 3)
        baseline.matrix = matrix.tolist()
        captures = acquire_pair(
            root,
            data,
            case_id,
            seed,
            level,
            pose,
            amplitude,
            profile=operating,
            baseline_pose=baseline,
        )
    else:
        captures = sorted(
            [c for c in load_public_observations(data) if isinstance(c, InspectionCapture)],
            key=lambda c: c.acquired_at,
        )
    prediction = output / "predictions" / case_id
    if prediction.exists():
        prediction = output / ("predictions-attempt-" + str(time.time_ns())) / case_id
    before_wall = time.perf_counter()
    before_cpu = time.process_time()
    reports = analyze_geometry(
        data / captures[0].artifact.uri,
        data / captures[1].artifact.uri,
        AnalyticsConfig(),
        load_reference(root / "configs/analytics/accepted_reference.json"),
        prediction,
        methods=["B3.1", "B3.2"],
        improved_calibration=json.loads(
            (root / "configs/fusion/calibration/geometry_b31.json").read_text()
        ),
        view_calibration=json.loads(
            (root / "configs/validation/view_calibration.json").read_text()
        ),
    )
    wall = time.perf_counter() - before_wall
    cpu = time.process_time() - before_cpu
    verify_seal(prediction)
    # The controller wrote latent truth separately. Only evaluator opens it after sealing both predictions.
    truth = json.loads((data / "evaluation_private/truth.json").read_text())
    fault = next(
        (
            f
            for f in truth["fault_states"]
            if f["category"] == "localized_geometric_deformation" and f["present"]
        ),
        None,
    )
    rows = []
    for method, (registration, geometry) in reports.items():
        matches = region_matches(geometry, fault)
        rows.append(
            {
                "case_id": case_id,
                "seed": seed,
                "partition": partition,
                "level": level,
                "view_group": pose_name,
                "operating": operating,
                "amplitude_m": amplitude,
                "method": method,
                "fault_present": bool(fault),
                "localized_detected": any(matches),
                "positive": geometry.status == "valid" and bool(geometry.regions),
                "regions": len(matches),
                "matched_regions": sum(matches),
                "false_regions": len(matches) - sum(matches),
                "status": geometry.status,
                "registration_status": registration.status,
                "calibration_applicable": not geometry.calibration_id.startswith("uncalibrated"),
                "calibration_id": geometry.calibration_id,
                "valid_patches": sum(
                    p.status == "valid" and p.calibration_support >= 10 for p in geometry.patches
                ),
                "patches": len(geometry.patches),
                "registration_runtime_s": registration.runtime_s,
                "geometry_runtime_s": geometry.runtime_s,
                "shared_wall_s": wall,
                "shared_cpu_s": cpu,
                "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                "prediction_dir": str(prediction.relative_to(root)),
                "public_manifest_sha256": hashlib.sha256(
                    (data / "manifest.json").read_bytes()
                ).hexdigest(),
            }
        )
    result = {"case_id": case_id, "rows": rows}
    atomic_json(done, result)
    return result


def detector_campaign(root, output, partition="development", workers=2, smoke=False, resume=False):
    root = Path(root).resolve()
    output = Path(output).resolve()
    settings = json.loads((root / "configs/validation/phase7.yaml").read_text())
    seeds = (
        settings["development_seeds"] if partition == "development" else settings["heldout_seeds"]
    )
    poses = standard_poses(root)
    tasks = []
    if smoke:
        seeds = seeds[:1]
        poses = {k: poses[k] for k in ("reference", "near_center")}
    for seed in seeds:
        for name, pose in poses.items():
            for amplitude in (0, 0.01, 0.02, 0.03, 0.05):
                operating = "increase" if seed % 3 == 0 else "steady"
                ident = "v7-" + partition + "-" + str(len(tasks)).zfill(5)
                tasks.append(
                    (
                        str(root),
                        str(output),
                        ident,
                        seed,
                        "L1",
                        name,
                        pose.model_dump(mode="json"),
                        amplitude,
                        operating,
                        partition,
                    )
                )
        if not smoke and partition == "heldout":
            for level in ("L0", "L2"):
                for name in ("reference", "far_oblique"):
                    for amplitude in (0, 0.02):
                        ident = "v7-heldout-" + str(len(tasks)).zfill(5)
                        tasks.append(
                            (
                                str(root),
                                str(output),
                                ident,
                                seed,
                                level,
                                name,
                                poses[name].model_dump(mode="json"),
                                amplitude,
                                "steady",
                                partition,
                            )
                        )
    sources = {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ("analytics", "inspection")
        for p in sorted((root / "src/twinguard" / folder).glob("*.py"))
    }
    configuration = {
        "purpose": "Independent detector validation",
        "partition": partition,
        "seeds": seeds,
        "count": len(tasks),
        "source_hashes": sources,
        "view_calibration_sha256": hashlib.sha256(
            (root / "configs/validation/view_calibration.json").read_bytes()
        ).hexdigest(),
        "legacy_calibration_sha256": hashlib.sha256(
            (root / "configs/fusion/calibration/geometry_b31.json").read_bytes()
        ).hexdigest(),
        "protocol": {
            "physical_pose_jitter_m": 0.035,
            "baseline_pose_jitter_m": 0.025,
            "amplitudes_m": [0, 0.01, 0.02, 0.03, 0.05],
            "operating": "One-third load-increase cases; other cases steady",
            "geometry": "Fresh fault centers and widths, all frozen before held-out generation",
        },
        "metrics_rule": "Strict valid-region/qualified-patch-center ellipse matching; unconditional and qualified-only counts separate",
    }
    campaign = Campaign(
        output, configuration, resume=resume, reserve_bytes=len(tasks) * 3 * 1024**2
    )
    todo = [t for t in tasks if t[2] not in campaign.state["completed"]]
    began = time.perf_counter()
    try:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for value in pool.map(detector_case, todo):
                campaign.commit(value["case_id"], value)
                print(value["case_id"], "done", len(campaign.state["completed"]), flush=True)
        campaign.finish(len(tasks))
        rows = [
            r
            for p in sorted((output / "cases").glob("*.json"))
            for r in json.loads(p.read_text())["rows"]
        ]
        summary = {}
        for method in ("B3.1", "B3.2"):
            group = [r for r in rows if r["method"] == method]
            positive = [r for r in group if r["fault_present"]]
            healthy = [r for r in group if not r["fault_present"]]
            summary[method] = {
                "cases": len(group),
                "healthy": len(healthy),
                "healthy_positive": sum(r["positive"] for r in healthy),
                "positive": len(positive),
                "localized_detected": sum(r["localized_detected"] for r in positive),
                "qualified_positive": sum(r["status"] == "valid" for r in positive),
                "qualified_positive_detected": sum(
                    r["localized_detected"] for r in positive if r["status"] == "valid"
                ),
                "inconclusive": sum(r["status"] != "valid" for r in group),
                "registration_failures": sum(r["registration_status"] != "valid" for r in group),
                "calibration_applicable": sum(r["calibration_applicable"] for r in group),
                "matched_regions": sum(r["matched_regions"] for r in group),
                "all_positive_regions": sum(r["regions"] for r in group),
            }
        atomic_json(
            output / "report.json",
            {
                "status": "executed",
                "partition": partition,
                "case_count": len(tasks),
                "elapsed_s": time.perf_counter() - began,
                "summary": summary,
                "rows": rows,
            },
        )
        return summary
    except BaseException as exc:
        campaign.fail(exc)
        raise
