"""First-visible-surface pinhole projection and grey-body radiometric surrogate."""

from datetime import timedelta
import numpy as np
from twinguard.core.contracts import InspectionCapture, Artifact
from twinguard.core.spatial import Frame
from .config import ThermalConfig
from .noise import perturb, reported_pose, resolve_pose
from .products import CaptureProduct
from .raycast import RayScene


def camera_directions(config: ThermalConfig):
    fx = config.width / (2 * np.tan(config.horizontal_fov_rad / 2))
    fy = config.height / (2 * np.tan(config.vertical_fov_rad / 2))
    cx = (config.width - 1) / 2
    cy = (config.height - 1) / 2
    u, v = np.meshgrid(np.arange(config.width), np.arange(config.height))
    directions = np.column_stack([np.ones(u.size), -(u.ravel() - cx) / fx, -(v.ravel() - cy) / fy])
    directions /= np.linalg.norm(directions, axis=1)[:, None]
    return directions, {"fx": fx, "fy": fy, "cx": cx, "cy": cy}


def apparent_temperature(surface_c, emissivity, reflected_c):
    return (
        emissivity * (np.asarray(surface_c) + 273.15) ** 4
        + (1 - emissivity) * (reflected_c + 273.15) ** 4
    ) ** 0.25 - 273.15


class ThermalSensor:
    def __init__(self, config: ThermalConfig):
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
            raise ValueError("Thermal acquisition pose frame mismatch")
        directions, intrinsics = camera_directions(c)
        matrix = np.asarray(actual_pose.matrix)
        scene = RayScene(physical, c.backend)
        hits = scene.cast(matrix[:3, 3], directions @ matrix[:3, :3].T)
        visible = (
            np.isfinite(hits.distance_m)
            & (hits.distance_m >= c.min_range_m)
            & (hits.distance_m <= c.max_range_m)
        )
        surface = scene.temperature(hits)
        reference = apparent_temperature(surface, c.emissivity, c.reflected_temperature_c)
        measured, _, _ = perturb(np.where(visible, reference, 0), c.noise, rng)
        valid = visible & (rng.random(len(measured)) >= c.noise.dropout)
        saturated = valid & ((measured < c.measurement_min_c) | (measured > c.measurement_max_c))
        measured = np.clip(measured, c.measurement_min_c, c.measurement_max_c)
        measured[~valid] = np.nan
        reported = reported_pose(actual_pose, c.pose_error, pose_rng)
        record = InspectionCapture(
            capture_id=event_id,
            mission_id="virtual-inspection",
            asset_ids=[c.asset_id],
            sensor_id=c.sensor_id,
            acquired_at=physical.timestamp,
            received_at=physical.timestamp + timedelta(seconds=c.reception_delay_s),
            modality="thermal",
            artifact=Artifact(
                artifact_id=event_id,
                uri=f"observations/thermal/{event_id}.npz",
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
            acquisition_parameters=intrinsics
            | {
                "width": c.width,
                "height": c.height,
                "emissivity": c.emissivity,
                "reflected_temperature_c": c.reflected_temperature_c,
                "noise_std_c": c.noise.sigma,
                "range_min_m": c.min_range_m,
                "range_max_m": c.max_range_m,
            },
            quality_indicators={
                "total_pixels": len(valid),
                "valid_pixels": int(valid.sum()),
                "valid_fraction": float(valid.mean()),
                "saturated_pixels": int(saturated.sum()),
            },
        )
        shape = (c.height, c.width)
        truth = {
            "true_pose": actual_pose.matrix,
            "surface_temperature_c": surface.reshape(shape),
            "noiseless_apparent_c": reference.reshape(shape),
            "measurement_error_c": (measured - reference).reshape(shape),
            "triangle_ids": hits.triangle_id.reshape(shape),
            "visible_mask": visible.reshape(shape),
        }
        return CaptureProduct(
            record,
            {"temperature_c": measured.reshape(shape), "valid_mask": valid.reshape(shape)},
            truth,
        )
