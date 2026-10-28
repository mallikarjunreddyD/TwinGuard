"""Independent healthy-only B3.2 view-domain calibration; original B3.1 remains immutable."""

from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ProcessPoolExecutor
import argparse
import json
import time
import hashlib
import numpy as np
from twinguard.evaluation.campaigns import Campaign, atomic_json, resource_preflight
from twinguard.evaluation.viewpoint_campaign import acquire_pair, standard_poses
from twinguard.analytics.clouds import load_scan
from twinguard.analytics.config import AnalyticsConfig
from twinguard.analytics.reference import load_reference
from twinguard.analytics.registration import register
from twinguard.analytics.geometric_improved import calibrate
from twinguard.analytics.view_calibration import acquisition_signature
from twinguard.analytics.pipeline import fingerprint
from twinguard.inspection.observations import load_config
from twinguard.inspection.coverage import ReferenceSurface
from twinguard.inspection.contracts import PlanningSnapshot, AssetPlanningState
from twinguard.inspection.candidates import generate
from twinguard.core.spatial import Transform

ROOT = Path(__file__).resolve().parents[1]


def prototypes():
    cfg = load_config(ROOT / "configs/inspection/planner.yaml")
    surface = ReferenceSurface(ROOT / cfg.reference_path, cfg.reference_sha256, cfg.cell_m)
    snapshot = PlanningSnapshot(
        snapshot_id="healthy-calibration-domain",
        at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        reference_hash=surface.hash,
        assets=[AssetPlanningState(asset_id="BW-01")],
    )
    views = [v for v in generate(surface, snapshot, cfg, ROOT) if v.modality == "lidar"]
    poses = [
        ("domain-" + str(i).zfill(2), v.planned_pose.model_dump(mode="json"))
        for i, v in enumerate(views)
    ]
    for name, pose in list(standard_poses(ROOT).items())[:2]:
        poses.append((name, pose.model_dump(mode="json")))
    return poses


def fit_domain(task):
    output, name, pose_json, seeds = task
    output = Path(output)
    work = output / "domains" / name
    config = AnalyticsConfig()
    ref = load_reference(ROOT / "configs/analytics/accepted_reference.json")
    pose = Transform.model_validate(pose_json)
    baseline_nominal = standard_poses(ROOT)["reference"]
    samples = []
    training = []
    rows = []
    signature = None
    for seed, fit in seeds:
        resource_preflight(reserve_bytes=20 * 1024**2)
        case = f"v7cal-{name}-{seed}"
        data = work / "datasets" / case
        rng = np.random.default_rng(seed)
        current = pose.model_copy(deep=True)
        base = baseline_nominal.model_copy(deep=True)
        matrix = np.array(current.matrix)
        matrix[:3, 3] += rng.uniform(-0.02, 0.02, 3)
        current.matrix = matrix.tolist()
        matrix = np.array(base.matrix)
        matrix[:3, 3] += rng.uniform(-0.015, 0.015, 3)
        base.matrix = matrix.tolist()
        captures = acquire_pair(
            ROOT, data, case, seed, "L1", current, baseline_pose=base, variation=False
        )
        b, c = [load_scan(data / r.artifact.uri, config) for r in captures]
        reg, registered = register(b, c, config, ref, "point_to_point")
        signature = acquisition_signature(b.record)
        atomic_json(data / "observations/estimated_registration.json", reg.model_dump(mode="json"))
        if reg.status == "valid":
            samples.append((b, registered, reg, fit))
        training.append(captures[1].provenance_id)
        rows.append(
            {
                "seed": seed,
                "partition": "fit" if fit else "screen",
                "registration_status": reg.status,
                "fitness": reg.fitness,
                "conditioning": reg.conditioning_ratio,
                "public_manifest_sha256": hashlib.sha256(
                    (data / "manifest.json").read_bytes()
                ).hexdigest(),
            }
        )
    model = calibrate(samples, config, ref, training)
    domain = {
        "domain_id": name,
        "baseline_pose": baseline_nominal.matrix,
        "current_pose": pose.matrix,
        "world_frame": baseline_nominal.target.model_dump(mode="json"),
        "sensor_signature": signature,
        "asset_ids": ["BW-01"],
        "maximum_pose_distance_m": 0.15,
        "maximum_pose_angle_rad": 0.08,
        "independent_fit_scans": sum(s[3] for s in samples),
        "independent_screen_scans": sum(not s[3] for s in samples),
        "model": model,
        "scope": "Operator-declared nominal pose domains, independently sampled healthy scans; not a physical sensor calibration or detection probability",
        "training_records": rows,
    }
    atomic_json(work / "profile.json", domain)
    return domain


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=(1, 2), default=2)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    profiles = prototypes()
    profiles = profiles[:1] if args.smoke else profiles
    cfg = json.loads((ROOT / "configs/validation/phase7.yaml").read_text())
    seeds = [(s, True) for s in cfg["healthy_calibration_fit_seeds"]] + [
        (s, False) for s in cfg["healthy_calibration_screen_seeds"]
    ]
    campaign = Campaign(
        args.output,
        {
            "purpose": "View-conditioned independent healthy calibration",
            "prototypes": profiles,
            "seed_partitions": seeds,
            "noise_profile": "Unchanged L1",
            "pose_jitter_m": 0.02,
            "baseline_jitter_m": 0.015,
            "count": len(profiles) * len(seeds),
        },
        reserve_bytes=len(profiles) * len(seeds) * 4 * 1024**2,
    )
    started = time.perf_counter()
    domains = []
    try:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for domain in pool.map(
                fit_domain, [(str(args.output), name, pose, seeds) for name, pose in profiles]
            ):
                domains.append(domain)
                campaign.commit(
                    domain["domain_id"],
                    {
                        "independent_fit_scans": domain["independent_fit_scans"],
                        "independent_screen_scans": domain["independent_screen_scans"],
                        "model_multiplier": domain["model"]["multipliers"],
                        "model_hash": fingerprint(domain["model"]),
                    },
                )
                print(
                    domain["domain_id"],
                    domain["independent_fit_scans"],
                    domain["independent_screen_scans"],
                    domain["model"]["multipliers"],
                    flush=True,
                )
        campaign.finish(len(profiles))
        bundle = {
            "calibration_id": "b32-view-"
            + fingerprint([d["model"]["calibration_id"] for d in domains])[:16],
            "algorithm_version": "v3.2-view-v1",
            "configuration_sha256": fingerprint(AnalyticsConfig()),
            "reference_sha256": fingerprint(
                load_reference(ROOT / "configs/analytics/accepted_reference.json")
            ),
            "domains": domains,
            "training_partition": cfg["healthy_calibration_fit_seeds"],
            "screen_partition": cfg["healthy_calibration_screen_seeds"],
            "elapsed_s": time.perf_counter() - started,
        }
        atomic_json(args.output / "view_calibration.json", bundle)
        print(
            "Calibration complete",
            len(domains),
            "domains",
            len(domains) * len(seeds),
            "actual healthy scan pairs",
            flush=True,
        )
    except BaseException as exc:
        campaign.fail(exc)
        raise


if __name__ == "__main__":
    main()
