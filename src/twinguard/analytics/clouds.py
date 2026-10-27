from dataclasses import dataclass
from pathlib import Path
import numpy as np
from twinguard.core.contracts import InspectionCapture
from twinguard.core.observations import load_public_observations, load_capture_arrays
from .config import AnalyticsConfig


@dataclass(frozen=True)
class MeasuredCloud:
    record: InspectionCapture
    original_sensor_m: np.ndarray
    processing_sensor_m: np.ndarray
    processing_world_m: np.ndarray


def preprocess(points, record: InspectionCapture, config: AnalyticsConfig):
    import open3d as o3d

    points = np.asarray(points, float)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("Expected measured Nx3 points")
    original = points.copy()
    radius = np.linalg.norm(points, axis=1)
    keep = (
        np.isfinite(points).all(axis=1)
        & (radius >= config.min_range_m)
        & (radius <= config.max_range_m)
    )
    selected = points[keep]
    if (
        record.artifact_coordinate_frame is None
        or record.artifact_coordinate_frame != record.sensor_pose.source
    ):
        raise ValueError("Sensor-local measured frame must be explicit")
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(selected))
    if config.statistical_outliers and len(selected) > config.outlier_neighbors:
        cloud, _ = cloud.remove_statistical_outlier(
            config.outlier_neighbors, config.outlier_std_ratio
        )
    cloud = cloud.voxel_down_sample(config.voxel_m)
    processed = np.asarray(cloud.points).copy()
    matrix = np.asarray(record.sensor_pose.matrix)
    world = processed @ matrix[:3, :3].T + matrix[:3, 3]
    return MeasuredCloud(record, original, processed, world)


def load_scan(path: Path, config: AnalyticsConfig):
    root = next((p for p in path.parents if (p / "manifest.json").exists()), None)
    if root is None:
        raise ValueError("Scan must belong to a public observation manifest")
    records = load_public_observations(root)
    record = next(
        (
            r
            for r in records
            if isinstance(r, InspectionCapture)
            and r.modality == "lidar"
            and r.capture_id == path.stem
        ),
        None,
    )
    if record is None:
        raise ValueError("Unknown public scan capture")
    return preprocess(load_capture_arrays(root, record)["points_m"], record, config)
