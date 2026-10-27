"""Order-independent SHA256-derived streams and instrument error utilities."""

import hashlib
import json
import numpy as np
from twinguard.core.spatial import Transform
from .config import PoseError, MeasurementNoise


def stream(
    seed: int, scenario_id: str, sensor_id: str, event_id: str, purpose: str = "measurement"
):
    payload = json.dumps([seed, scenario_id, sensor_id, event_id, purpose], separators=(",", ":"))
    words = np.frombuffer(hashlib.sha256(payload.encode()).digest(), dtype="<u4")
    return np.random.default_rng(np.random.SeedSequence(words.tolist()))


def rotation_xyz(angles):
    x, y, z = angles
    cx, sx = np.cos(x), np.sin(x)
    cy, sy = np.cos(y), np.sin(y)
    cz, sz = np.cos(z), np.sin(z)
    return (
        np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
        @ np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
        @ np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    )


def reported_pose(actual: Transform, config: PoseError, rng):
    translation = rng.normal(0, config.translation_sigma_m, 3) + config.translation_bias_m
    angles = rng.normal(0, config.rotation_sigma_rad, 3) + config.rotation_bias_rad
    matrix = np.asarray(actual.matrix).copy()
    matrix[:3, 3] += translation
    matrix[:3, :3] = rotation_xyz(angles) @ matrix[:3, :3]
    return Transform(source=actual.source, target=actual.target, matrix=matrix.tolist())


def perturb(values, config: MeasurementNoise, rng):
    values = np.asarray(values, float)
    sigma = config.sigma + config.range_slope * np.abs(values)
    measured = values + config.bias + rng.normal(0, 1, values.shape) * sigma
    outliers = rng.random(values.shape) < config.outlier_probability
    measured += outliers * rng.uniform(-config.outlier_scale, config.outlier_scale, values.shape)
    if config.quantum:
        measured = np.round(measured / config.quantum) * config.quantum
    return measured, sigma, outliers


def resolve_pose(physical, pose: Transform) -> Transform:
    """Resolve a configured asset-parent sensor transform into the current world."""
    if pose.target == physical.coordinate_frame:
        return pose
    if pose.target.kind == "asset_local":
        parent = next(
            (
                surface
                for surface in physical.surfaces
                if surface.asset_id == pose.target.reference_id
            ),
            None,
        )
        if parent is not None and parent.world_pose is not None:
            return parent.world_pose.compose(pose)
    raise ValueError("Cannot resolve sensor parent pose into physical world")
