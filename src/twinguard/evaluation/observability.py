"""Restricted-only spatial observability audit; never used to tune held-out inference."""

from pathlib import Path
import json
import numpy as np
from scipy.spatial import ConvexHull, QhullError
from twinguard.core.contracts import InspectionCapture
from twinguard.core.observations import load_public_observations


def deformation_audit(root: Path, roi=None, cell_m=0.1, min_returns=12, min_fraction=0.15):
    context = json.loads((root / "evaluation_private/plant_truth.json").read_text())
    scenario = json.loads((root / "evaluation_private/scenario.json").read_text())
    faults = context["ground_truth_snapshots"][0]["fault_states"]
    deformation = next(
        (f["configuration"] for f in faults if f["category"] == "localized_geometric_deformation"),
        None,
    )
    roi = roi or (
        dict(
            asset_id=deformation["asset_id"],
            center_local_m=deformation["center_local_m"],
            extent_m=deformation["extent_m"],
        )
        if deformation
        else dict(asset_id="BW-01", center_local_m=[0, 0, 1.2], extent_m=[0.4, 0.1, 0.5])
    )
    from twinguard.plant.config import PlantConfig
    from twinguard.plant.model import create_baseline_plant

    baseline = create_baseline_plant(
        PlantConfig.model_validate(context["plant_config"]), scenario["random_seed"]
    )
    transform = np.asarray(baseline.world_pose(roi["asset_id"]).inverse().matrix)
    center = np.asarray(roi["center_local_m"])
    extent = np.asarray(roi["extent_m"])
    x = np.arange(center[0] - extent[0], center[0] + extent[0], cell_m) + cell_m / 2
    z = np.arange(center[2] - extent[2], center[2] + extent[2], cell_m) + cell_m / 2
    accepted = {
        (i, j)
        for i, a in enumerate(x)
        for j, b in enumerate(z)
        if ((a - center[0]) / extent[0]) ** 2 + ((b - center[2]) / extent[2]) ** 2 <= 1
    }
    frames = []
    occupied_sets = []
    for record in load_public_observations(root):
        if not isinstance(record, InspectionCapture) or record.modality != "lidar":
            continue
        with np.load(
            root / "evaluation_private" / f"{record.capture_id}.npz", allow_pickle=False
        ) as data:
            complete = "all_hit_world_m" in data
            world = data["all_hit_world_m"] if complete else data["surface_world_m"]
            assets = data["all_hit_asset_ids"] if complete else data["asset_ids"]
            valid = data["all_valid_returns"] if complete else np.ones(len(world), bool)
            local = world @ transform[:3, :3].T + transform[:3, 3]
            radius = ((local[:, 0] - center[0]) / extent[0]) ** 2 + (
                (local[:, 2] - center[2]) / extent[2]
            ) ** 2
            hit = (assets == roi["asset_id"]) & np.isfinite(local).all(1) & (radius <= 1)
            observed = local[hit & valid]
            cells = {
                (
                    int(np.floor((p[0] - center[0] + extent[0]) / cell_m)),
                    int(np.floor((p[2] - center[2] + extent[2]) / cell_m)),
                )
                for p in observed
            }
            cells &= accepted
            occupied_sets.append(cells)
            area = np.pi * extent[0] * extent[2]
            try:
                footprint = (
                    float(ConvexHull(observed[:, [0, 2]]).volume) if len(observed) >= 3 else 0.0
                )
            except QhullError:
                footprint = 0.0
            fraction = len(cells) / max(len(accepted), 1)
            frames.append(
                {
                    "capture_id": record.capture_id,
                    "time_s": (
                        record.acquired_at
                        - __import__("datetime").datetime.fromisoformat(
                            scenario["simulation_start"].replace("Z", "+00:00")
                        )
                    ).total_seconds(),
                    "all_region_hit_rays": int(hit.sum()) if complete else None,
                    "valid_region_returns": len(observed),
                    "projected_region_area_m2": float(area),
                    "sampling_density_returns_m2": len(observed) / area,
                    "occupied_cell_fraction": fraction,
                    "sample_footprint_area_m2": footprint,
                    "sample_footprint_fraction": min(1, footprint / area),
                    "observed_bounds_local_m": np.stack([observed.min(0), observed.max(0)]).tolist()
                    if len(observed)
                    else None,
                    "observable_at_grid_resolution": bool(
                        len(observed) >= min_returns and fraction >= min_fraction
                    ),
                    "all_ray_accounting_available": complete,
                }
            )
    common = set.intersection(*occupied_sets) if occupied_sets else set()
    return {
        "audit_kind": "restricted ground-truth observability; never an analytics threshold input",
        "roi": roi,
        "resolution_m": cell_m,
        "criterion": {
            "min_returns": min_returns,
            "min_occupied_fraction": min_fraction,
            "min_common_fraction": 0.1,
        },
        "captures": frames,
        "common_observed_cell_fraction": len(common) / max(len(accepted), 1),
        "pair_observable": bool(
            frames
            and all(f["observable_at_grid_resolution"] for f in frames)
            and len(common) / max(len(accepted), 1) >= 0.1
        ),
        "limitations": "Projected occupancy and convex sample footprint are estimates, not continuous visible surface area; legacy scans cannot recover dropped-ray accounting",
    }
