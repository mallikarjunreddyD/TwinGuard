"""Ray geometry, sensor uncertainty and radiometry verification (no analytics)."""

from datetime import datetime, timezone
import numpy as np
import pytest
from twinguard.core.spatial import Frame, Transform
from twinguard.sensing.config import LidarConfig, ThermalConfig, MeasurementNoise, PoseError
from twinguard.sensing.read import PhysicalReadView, Surface
from twinguard.sensing.raycast import RayScene
from twinguard.sensing.lidar import LidarSensor
from twinguard.sensing.thermal import ThermalSensor, apparent_temperature
from twinguard.sensing.noise import stream

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def plane(x=5, temperature=100, asset="front", size=10):
    vertices = np.array(
        [[x, -size, -size], [x, size, -size], [x, size, size], [x, -size, size]], float
    )
    return Surface(
        asset, vertices, np.array([[0, 1, 2], [0, 2, 3]]), np.full(4, temperature, dtype=float)
    )


def view(*surfaces):
    return PhysicalReadView(
        NOW,
        800000,
        180,
        0.5,
        tuple(surfaces),
        Frame(kind="world", reference_id="plant-01"),
        "v1",
        "v1",
        25,
    )


def config(kind="lidar", **kwargs):
    sensor = kind + "-01"
    pose = Transform(
        source=Frame(kind="sensor_local", reference_id=sensor),
        target=Frame(kind="world", reference_id="plant-01"),
        matrix=np.eye(4).tolist(),
    )
    args = dict(
        sensor_id=sensor,
        asset_id="front",
        source_type="synthetic",
        configuration_version="v1",
        description="Synthetic geometry test instrument",
        coordinate_frame=pose.source,
        pose=pose,
    )
    args.update(kwargs)
    return (LidarConfig if kind == "lidar" else ThermalConfig)(**args)


def capture(sensor, physical, seed=42, event="event-01"):
    return sensor.capture(
        physical,
        event,
        "synthetic-fixture",
        stream(seed, "fixture", sensor.config.sensor_id, event),
        stream(seed, "fixture", sensor.config.sensor_id, event, "pose"),
    )


def test_ray_first_hit_occlusion_and_miss():
    scene = RayScene(view(plane(5, 200, "hidden"), plane(3, 20, "front")))
    result = scene.cast([0, 0, 0], [[1, 0, 0], [-1, 0, 0], [0, 1, 0]])
    assert result.distance_m[0] == pytest.approx(3, abs=1e-10)
    assert np.isinf(result.distance_m[1:]).all()
    assert scene.asset_ids[result.triangle_id[0]] == "front"
    assert scene.temperature(result)[0] == pytest.approx(20)
    assert np.allclose(result.barycentric[0].sum(), 1)


def test_barycentric_temperature_interpolation():
    triangle = Surface(
        "gradient",
        np.array([[5, -1, -1], [5, 1, -1], [5, 0, 1]], float),
        np.array([[0, 1, 2]]),
        np.array([100, 200, 300], float),
    )
    scene = RayScene(view(triangle))
    hit = scene.cast([0, 0, 0], [[1, 0, 0]])
    assert np.allclose(hit.barycentric[0], [0.25, 0.25, 0.5])
    assert scene.temperature(hit)[0] == pytest.approx(225)


def test_ideal_lidar_frame_and_limits():
    physical = view(plane())
    result = capture(
        LidarSensor(
            config(channels=3, horizontal_samples=11, vertical_min_rad=-0.1, vertical_max_rad=0.1)
        ),
        physical,
    )
    assert np.allclose(result.arrays["points_m"][:, 0], 5, atol=2e-5)
    assert len(result.arrays["points_m"]) == 33
    assert np.max(np.abs(result.evaluation_private["range_errors_m"])) < 2e-5
    assert result.observation.artifact_coordinate_frame.kind == "sensor_local"
    for kwargs in ({"max_range_m": 4}, {"min_range_m": 15}):
        empty = capture(LidarSensor(config(**kwargs)), physical)
        assert empty.arrays["points_m"].shape == (0, 3)
    # An object before min range still occludes a farther object.
    empty = capture(
        LidarSensor(
            config(
                min_range_m=4, horizontal_fov_rad=0.1, vertical_min_rad=-0.05, vertical_max_rad=0.05
            )
        ),
        view(plane(3), plane(5)),
    )
    assert empty.arrays["points_m"].shape == (0, 3)


def test_lidar_transformed_frame():
    c = config(channels=1, horizontal_samples=1, vertical_min_rad=0, vertical_max_rad=0)
    matrix = np.eye(4)
    matrix[:3, 3] = [1, 0, 0]
    c.pose = Transform(source=c.pose.source, target=c.pose.target, matrix=matrix.tolist())
    result = capture(LidarSensor(c), view(plane()))
    assert np.allclose(result.arrays["points_m"], [[4, 0, 0]])
    assert np.allclose(c.pose.apply(result.arrays["points_m"].tolist(), c.pose.source), [[5, 0, 0]])


def test_lidar_noise_statistics_pose_and_dropout():
    c = config(
        channels=16,
        horizontal_samples=720,
        horizontal_fov_rad=0.2,
        vertical_min_rad=-0.1,
        vertical_max_rad=0.1,
        noise=MeasurementNoise(sigma=0.02, bias=0.004, dropout=0.2),
        pose_error=PoseError(translation_sigma_m=0.03, rotation_sigma_rad=0.01),
    )
    result = capture(LidarSensor(c), view(plane()))
    error = result.evaluation_private["range_errors_m"]
    assert abs(error.mean() - 0.004) < 0.001
    assert abs(error.std() - 0.02) < 0.001
    fraction = result.observation.quality_indicators["return_fraction"]
    assert 0.77 < fraction < 0.83
    assert not np.array_equal(
        result.evaluation_private["true_pose"], result.observation.sensor_pose.matrix
    )
    repeat = capture(LidarSensor(c), view(plane()))
    assert np.array_equal(result.arrays["points_m"], repeat.arrays["points_m"])
    assert not np.array_equal(
        result.arrays["points_m"],
        capture(LidarSensor(c), view(plane()), seed=43).arrays["points_m"],
    )


def test_lidar_angular_quantization_outliers():
    c = config(
        channels=4,
        horizontal_samples=300,
        noise=MeasurementNoise(
            angular_sigma_rad=0.01,
            quantum=0.005,
            outlier_probability=0.05,
            outlier_scale=1,
            incidence_dropout=0.1,
        ),
    )
    product = capture(LidarSensor(c), view(plane()))
    ranges = np.linalg.norm(product.arrays["points_m"], axis=1)
    assert np.allclose(ranges / 0.005, np.round(ranges / 0.005))
    assert product.evaluation_private["outliers"].sum() > 20
    assert np.std(product.arrays["points_m"][:, 0]) > 0.01


def test_thermal_uniform_gradient_and_occlusion():
    c = config("thermal", width=21, height=15, emissivity=1)
    product = capture(ThermalSensor(c), view(plane(5, 120)))
    assert product.arrays["valid_mask"].all()
    assert np.allclose(product.arrays["temperature_c"], 120)
    hidden = capture(ThermalSensor(c), view(plane(3, 30), plane(5, 250, "hidden-hotspot")))
    assert np.allclose(hidden.arrays["temperature_c"], 30)
    gradient = plane(5, 0)
    gradient.temperature_c[:] = [0, 100, 100, 0]
    image = capture(ThermalSensor(c), view(gradient)).arrays["temperature_c"]
    assert np.ptp(image) > 10
    assert np.isfinite(image).all()


def test_emissivity_kelvin_and_measurement_noise():
    assert apparent_temperature(100, 1, 25) == pytest.approx(100)
    assert apparent_temperature(100, 0, 25) == pytest.approx(25)
    assert 25 < apparent_temperature(100, 0.5, 25) < 100
    c = config(
        "thermal",
        width=100,
        height=100,
        emissivity=0.9,
        noise=MeasurementNoise(sigma=0.7, bias=0.2, dropout=0.15),
    )
    product = capture(ThermalSensor(c), view(plane(5, 120)))
    valid = product.arrays["valid_mask"]
    error = product.evaluation_private["measurement_error_c"][valid]
    assert abs(error.mean() - 0.2) < 0.04
    assert abs(error.std() - 0.7) < 0.04
    assert 0.82 < valid.mean() < 0.88
    assert np.isnan(product.arrays["temperature_c"][~valid]).all()


def test_thermal_saturation_misses_and_viewpoint():
    c = config("thermal", width=9, height=9, emissivity=1, measurement_max_c=80)
    saturated = capture(ThermalSensor(c), view(plane(5, 120)))
    assert saturated.observation.quality_indicators["saturated_pixels"] == 81
    assert np.all(saturated.arrays["temperature_c"] == 80)
    c.pose.matrix[0][3] = 6
    missing = capture(ThermalSensor(c), view(plane(5, 120)))
    assert not missing.arrays["valid_mask"].any()
    assert np.isnan(missing.arrays["temperature_c"]).all()


def test_cpu_backends_agree():
    physical = view(plane(3, 25), plane(5, 200, "back"))
    directions = np.column_stack([np.ones(100), np.linspace(-0.5, 0.5, 100), np.zeros(100)])
    a = RayScene(physical, "open3d").cast([0, 0, 0], directions)
    b = RayScene(physical, "numpy_bvh").cast([0, 0, 0], directions)
    assert np.allclose(a.distance_m, b.distance_m, atol=2e-5)
    assert np.array_equal(a.triangle_id >= 0, b.triangle_id >= 0)


def test_actual_wall_deformation_is_observed_by_independent_rays():
    from pathlib import Path
    from twinguard.plant.io import simulator_from_scenario
    from twinguard.sensing.acquisition import load_installation

    root = Path(__file__).resolve().parents[1]
    c = load_installation(root / "configs/sensing/L0.yaml").lidar
    c.channels = 1
    c.horizontal_samples = 1
    c.vertical_min_rad = 0
    c.vertical_max_rad = 0
    c.pose.matrix[2][3] = 1.55
    healthy = simulator_from_scenario(root / "scenarios/S0.yaml", root)
    deformed = simulator_from_scenario(root / "scenarios/S2.yaml", root)
    a = capture(LidarSensor(c), healthy.sensing_reader().read_at(60))
    b = capture(LidarSensor(c), deformed.sensing_reader().read_at(60))
    assert np.linalg.norm(a.arrays["points_m"][0]) - np.linalg.norm(
        b.arrays["points_m"][0]
    ) == pytest.approx(0.03, abs=2e-5)


@pytest.mark.parametrize("level", ["L0", "L1", "moderate", "L2"])
def test_explicit_fidelity_presets(level):
    from pathlib import Path
    from twinguard.sensing.acquisition import load_installation

    root = Path(__file__).resolve().parents[1]
    installation = load_installation(root / f"configs/sensing/{level}.yaml")
    assert len(installation.iot) == 9
    assert installation.lidar.channels == 16
    if level == "L0":
        assert installation.lidar.noise.sigma == 0
    if level == "L2":
        assert installation.lidar.noise.sigma > 0.003


def test_parent_asset_pose_is_resolved_in_current_world():
    from dataclasses import replace

    parent = Frame(kind="asset_local", reference_id="front")
    world = Frame(kind="world", reference_id="plant-01")
    matrix = np.eye(4)
    matrix[:3, 3] = [1, 0, 0]
    surface = replace(
        plane(), world_pose=Transform(source=parent, target=world, matrix=matrix.tolist())
    )
    c = config(channels=1, horizontal_samples=1, vertical_min_rad=0, vertical_max_rad=0)
    c.pose = Transform(source=c.pose.source, target=parent, matrix=np.eye(4).tolist())
    result = capture(LidarSensor(c), view(surface))
    assert np.allclose(result.arrays["points_m"], [[4, 0, 0]], atol=2e-5)
    assert result.observation.sensor_pose.target == world
    assert result.observation.sensor_pose.matrix[0][3] == 1
