"""Independently raycast scans with instrument-frame measured returns."""

from datetime import timedelta
import numpy as np
from twinguard.core.contracts import InspectionCapture, Artifact
from twinguard.core.spatial import Frame
from .config import LidarConfig
from .products import CaptureProduct
from .raycast import RayScene
from .noise import perturb, reported_pose, resolve_pose


def scanning_directions(config: LidarConfig, rng):
    horizontal = config.sweep_center_rad + np.linspace(
        -config.horizontal_fov_rad / 2,
        config.horizontal_fov_rad / 2,
        config.horizontal_samples,
        endpoint=config.horizontal_fov_rad < 2 * np.pi,
    )
    vertical = (
        np.linspace(config.vertical_min_rad, config.vertical_max_rad, config.channels)
        if config.channels > 1
        else np.array([(config.vertical_min_rad + config.vertical_max_rad) / 2])
    )
    if config.horizontal_samples == 1:
        horizontal = np.array([config.sweep_center_rad])
    az, el = np.meshgrid(horizontal, vertical)
    az, el = az.ravel(), el.ravel()

    def directions(a, e):
        return np.column_stack([np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)])

    nominal = directions(az, el)
    actual = directions(
        az + rng.normal(0, config.noise.angular_sigma_rad, len(az)),
        el + rng.normal(0, config.noise.angular_sigma_rad, len(el)),
    )
    return nominal, actual


class LidarSensor:
    def __init__(self, config: LidarConfig):
        self.config = config.model_copy(deep=True)

    def capture(
        self, physical, event_id, provenance_id, rng, pose_rng, pose=None
    ) -> CaptureProduct:
        c = self.config
        actual_pose = resolve_pose(physical, pose or c.pose)
        if (
            actual_pose.source != Frame(kind="sensor_local", reference_id=c.sensor_id)
            or actual_pose.target != physical.coordinate_frame
        ):
            raise ValueError("LiDAR acquisition pose frame mismatch")
        nominal, directions = scanning_directions(c, rng)
        matrix = np.asarray(actual_pose.matrix)
        scene = RayScene(physical, c.backend)
        hits = scene.cast(matrix[:3, 3], directions @ matrix[:3, :3].T)
        visible = np.isfinite(hits.distance_m)
        eligible = visible & (hits.distance_m >= c.min_range_m) & (hits.distance_m <= c.max_range_m)
        safe = np.where(visible, hits.distance_m, 0)
        measured, sigma, outliers = perturb(safe, c.noise, rng)
        dropout = np.minimum(
            1, c.noise.dropout + c.noise.incidence_dropout * (1 - hits.incidence_cosine)
        )
        valid = (
            eligible
            & (rng.random(len(measured)) >= dropout)
            & (measured >= c.min_range_m)
            & (measured <= c.max_range_m)
        )
        points = nominal[valid] * measured[valid, None]
        reported = reported_pose(actual_pose, c.pose_error, pose_rng)
        record = InspectionCapture(
            capture_id=event_id,
            mission_id="virtual-inspection",
            asset_ids=[c.asset_id],
            sensor_id=c.sensor_id,
            acquired_at=physical.timestamp,
            received_at=physical.timestamp + timedelta(seconds=c.reception_delay_s),
            modality="lidar",
            artifact=Artifact(
                artifact_id=event_id,
                uri=f"observations/lidar/{event_id}.npz",
                media_type="application/x-npz",
            ),
            coordinate_frame=reported.target,
            artifact_coordinate_frame=reported.source,
            sensor_pose=reported,
            calibration_id=c.calibration_reference or "assumed-calibration",
            provenance_id=provenance_id,
            configuration_version=c.configuration_version,
            source_type="synthetic",
            reported_translation_std_m=c.pose_error.translation_sigma_m,
            reported_rotation_std_rad=c.pose_error.rotation_sigma_rad,
            acquisition_parameters={
                "channels": c.channels,
                "horizontal_samples": c.horizontal_samples,
                "horizontal_fov_rad": c.horizontal_fov_rad,
                "vertical_min_rad": c.vertical_min_rad,
                "vertical_max_rad": c.vertical_max_rad,
                "range_min_m": c.min_range_m,
                "range_max_m": c.max_range_m,
                "range_sigma_m": c.noise.sigma,
                "range_slope": c.noise.range_slope,
                "angular_sigma_rad": c.noise.angular_sigma_rad,
            },
            quality_indicators={
                "emitted_rays": len(valid),
                "valid_returns": int(valid.sum()),
                "return_fraction": float(valid.mean()),
            },
        )
        truth = {
            "true_pose": actual_pose.matrix,
            "noiseless_range_m": hits.distance_m[valid],
            "measured_range_m": measured[valid],
            "range_errors_m": measured[valid] - hits.distance_m[valid],
            "surface_world_m": matrix[:3, 3]
            + (directions[valid] * hits.distance_m[valid, None]) @ matrix[:3, :3].T,
            "triangle_ids": hits.triangle_id[valid],
            "asset_ids": scene.asset_ids[hits.triangle_id[valid]],
            "sigma_m": sigma[valid],
            "outliers": outliers[valid],
            "visible_ray_count": int(visible.sum()),
            "eligible_ray_count": int(eligible.sum()),
            "emitted_ray_count": len(valid),
        }
        return CaptureProduct(record, {"points_m": points, "valid_returns": valid}, truth)
