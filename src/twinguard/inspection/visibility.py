"""Nominal first-hit predictions using actual angular sampling; no future physical mesh."""

import numpy as np


def look_at(position, target, sensor_id):
    from twinguard.core.spatial import Transform, Frame

    x = np.asarray(target) - position
    x = x / np.linalg.norm(x)
    up = np.array([0.0, 0.0, 1.0])
    if abs(x @ up) > 0.99:
        up = np.array([0.0, 1.0, 0.0])
    y = np.cross(up, x)
    y /= np.linalg.norm(y)
    z = np.cross(x, y)
    m = np.eye(4)
    m[:3, :3] = np.column_stack([x, y, z])
    m[:3, 3] = position
    return Transform(
        source=Frame(kind="sensor_local", reference_id=sensor_id),
        target=Frame(kind="world", reference_id="plant-01"),
        matrix=m.tolist(),
    )


def directions(sensor, modality):
    if modality == "lidar":
        az = np.linspace(
            -sensor["horizontal_fov_rad"] / 2,
            sensor["horizontal_fov_rad"] / 2,
            sensor["horizontal_samples"],
            endpoint=sensor["horizontal_fov_rad"] < 2 * np.pi,
        ) + sensor.get("sweep_center_rad", 0)
        el = (
            np.linspace(sensor["vertical_min_rad"], sensor["vertical_max_rad"], sensor["channels"])
            if sensor["channels"] > 1
            else np.array([(sensor["vertical_min_rad"] + sensor["vertical_max_rad"]) / 2])
        )
        a, e = np.meshgrid(az, el)
        return np.column_stack(
            [
                np.cos(e.ravel()) * np.cos(a.ravel()),
                np.cos(e.ravel()) * np.sin(a.ravel()),
                np.sin(e.ravel()),
            ]
        )
    # Existing thermal camera uses sensor +X forward, +Y left and +Z up.
    y = (1 - 2 * (np.arange(sensor["width"]) + 0.5) / sensor["width"]) * np.tan(
        sensor["horizontal_fov_rad"] / 2
    )
    z = (1 - 2 * (np.arange(sensor["height"]) + 0.5) / sensor["height"]) * np.tan(
        sensor["vertical_fov_rad"] / 2
    )
    yy, zz = np.meshgrid(y, z)
    d = np.column_stack([np.ones(yy.size), yy.ravel(), zz.ravel()])
    return d / np.linalg.norm(d, axis=1)[:, None]


def predict(surface, pose, sensor, modality, asset, config):
    m = np.asarray(pose.matrix)
    r, cos, cells = surface.cast(m[:3, 3], directions(sensor, modality) @ m[:3, :3].T)
    valid = (
        np.isfinite(r)
        & (r >= max(sensor["min_range_m"], config.minimum_standoff_m))
        & (r <= min(sensor["max_range_m"], config.maximum_range_m))
    )
    target = np.zeros(len(cells), bool)
    target[valid] = surface.assets[cells[valid]] == asset
    visible = sorted(set(cells[valid & target].tolist()))
    suitable = valid & target & (cos >= config.minimum_incidence_cosine)
    usable = sorted(set(cells[suitable].tolist()))
    distance = float(np.median(r[target & valid])) if np.any(target & valid) else 0
    incidence = float(np.mean(cos[target & valid])) if np.any(target & valid) else 0
    if modality == "lidar":
        angular = max(
            sensor["horizontal_fov_rad"] / max(1, sensor["horizontal_samples"] - 1),
            (sensor["vertical_max_rad"] - sensor["vertical_min_rad"])
            / max(1, sensor["channels"] - 1),
        )
        spacing = distance * np.tan(angular) / max(incidence, 0.01)
    else:
        spacing = (
            distance
            * max(
                2 * np.tan(sensor["horizontal_fov_rad"] / 2) / sensor["width"],
                2 * np.tan(sensor["vertical_fov_rad"] / 2) / sensor["height"],
            )
            / max(incidence, 0.01)
        )
    return visible, usable, distance, incidence, spacing, int(valid.sum())
