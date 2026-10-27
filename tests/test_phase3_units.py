from datetime import datetime, timezone, timedelta
import numpy as np
from twinguard.core.contracts import InspectionCapture, Artifact, SensorObservation
from twinguard.core.spatial import Frame, Transform
from twinguard.core.analytics_contracts import RegistrationResult
from twinguard.analytics.config import AnalyticsConfig
from twinguard.analytics.reference import AcceptedReference, ReferenceAsset
from twinguard.analytics.clouds import preprocess
from twinguard.analytics.registration import register
from twinguard.analytics.geometry import detect_geometry
from twinguard.analytics.operating import causal_load, calibrate_operating, infer_operating
from twinguard.analytics.thermal import quantitative_mask
from twinguard.core.observations import ObservationManifest, ObservationReference
from twinguard.core.contracts import DatasetProvenance

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def capture(identifier="scan", pose=None):
    frame = Frame(kind="sensor_local", reference_id="lidar")
    world = Frame(kind="world", reference_id="plant-01")
    return InspectionCapture(
        capture_id=identifier,
        mission_id="test",
        asset_ids=["deliberately-wrong-target"],
        sensor_id="lidar",
        acquired_at=NOW,
        received_at=NOW,
        modality="lidar",
        artifact=Artifact(
            artifact_id=identifier,
            uri="observations/lidar/" + identifier + ".npz",
            media_type="application/x-npz",
        ),
        coordinate_frame=world,
        artifact_coordinate_frame=frame,
        sensor_pose=Transform(
            source=frame, target=world, matrix=np.eye(4).tolist() if pose is None else pose
        ),
        calibration_id="fixture",
        provenance_id="fixture",
        reported_translation_std_m=0.02,
        reported_rotation_std_rad=0.01,
    )


def reference():
    return AcceptedReference(
        reference_id="accepted-test",
        provenance="fixed synthetic test fixture",
        assets=[
            ReferenceAsset(
                asset_id="BW-01",
                bounds_world_m=((-1, -0.1, 0), (1, 0.1, 3)),
                plane_point_world_m=(0, 0, 0),
                normal_world=(0, 1, 0),
            )
        ],
    )


def valid_registration(record):
    return RegistrationResult(
        registration_id="test-reg",
        baseline_capture_id=record.capture_id,
        current_capture_id="current",
        transform=Transform(
            source=record.sensor_pose.source,
            target=record.sensor_pose.source,
            matrix=np.eye(4).tolist(),
        ),
        method="point_to_point",
        status="valid",
        converged=True,
        fitness=1,
        inlier_rmse_m=0,
        correspondence_count=100,
        conditioning_ratio=0.1,
        uncertainty_score_m=0.001,
        repeatability_m=0,
        quality_flags=[],
        runtime_s=0,
    )


def test_icp_known_rigid_transform_and_robust_registration():
    rng = np.random.default_rng(17)
    points = rng.uniform(-0.5, 0.5, (1600, 3))
    axis = rng.integers(0, 3, len(points))
    sign = rng.choice([-1, 1], len(points))
    points[np.arange(len(points)), axis] = 0.5 * sign
    points += [1, 0, 1]
    angle = 0.02
    true = np.eye(4)
    true[:2, :2] = [[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]]
    true[:3, 3] = [0.015, -0.01, 0.008]
    current = (points - true[:3, 3]) @ true[:3, :3]
    config = AnalyticsConfig(min_correspondences=20, monitored_assets=[])
    b = preprocess(points, capture("baseline"), config)
    c = preprocess(current, capture("current"), config)
    for method in ("point_to_point", "robust_point_to_plane"):
        result, aligned = register(b, c, config, reference(), method)
        assert result.status == "valid", result.quality_flags
        assert np.linalg.norm(np.asarray(result.transform.matrix)[:3, 3] - true[:3, 3]) < 0.003
        assert np.allclose(result.transform.matrix, true, atol=0.003)
        assert len(aligned) == len(c.processing_sensor_m)


def test_registration_rejects_plane_ambiguity_and_empty_overlap():
    x, z = np.meshgrid(np.linspace(-0.8, 0.8, 35), np.linspace(0.2, 2.8, 35))
    plane = np.column_stack([x.ravel(), np.zeros(x.size), z.ravel()])
    config = AnalyticsConfig(monitored_assets=[])
    b = preprocess(plane, capture("b"), config)
    c = preprocess(plane, capture("c"), config)
    result, _ = register(b, c, config, reference(), "robust_point_to_plane")
    assert result.status != "valid"
    assert "weakly_constrained_geometry" in result.quality_flags
    empty = preprocess(np.empty((0, 3)), capture("empty"), config)
    result, _ = register(b, empty, config, reference())
    assert result.status != "valid" and result.correspondence_count == 0


def test_preprocessing_filters_and_preserves_original():
    points = np.array([[1, 0, 0], [np.nan, 0, 0], [100, 0, 0], [1.001, 0, 0]])
    cloud = preprocess(points, capture(), AnalyticsConfig(voxel_m=0.02))
    assert len(cloud.original_sensor_m) == 4
    assert len(cloud.processing_sensor_m) < 3
    assert np.isfinite(cloud.processing_sensor_m).all()


def test_patch_displacement_sign_uncertainty_and_missing_coverage():
    x, z = np.meshgrid(np.linspace(-0.9, 0.9, 65), np.linspace(0.2, 2.8, 81))
    points = np.column_stack([x.ravel(), np.zeros(x.size), z.ravel()])
    config = AnalyticsConfig(uncertainty_floor_m=0.001)
    b = preprocess(points, capture(), config)
    reg = valid_registration(b.record)
    current = b.processing_world_m.copy()
    radius = (current[:, 0] / 0.4) ** 2 + ((current[:, 2] - 1.5) / 0.5) ** 2
    current[:, 1] += 0.03 * np.maximum(0, 1 - radius) ** 3
    result = detect_geometry(b, current, reg, reference(), config)
    assert result.significant
    assert result.regions[0].asset_id == "BW-01"
    assert max(p.displacement_m or 0 for p in result.patches) > 0.015
    assert all(p.direction == "oriented" for p in result.patches if p.status == "valid")
    assert all(p.uncertainty_score_m >= 0.001 for p in result.patches if p.status == "valid")
    healthy = detect_geometry(b, b.processing_world_m, reg, reference(), config)
    assert healthy.significant is False
    missing = detect_geometry(b, np.empty((0, 3)), reg, reference(), config)
    assert missing.significant is None and missing.status == "insufficient_coverage"
    assert b.record.asset_ids == ["deliberately-wrong-target"]


def test_opposite_layers_are_not_treated_as_matching_surface():
    x, z = np.meshgrid(np.linspace(-0.9, 0.9, 60), np.linspace(0.2, 2.8, 70))
    points = np.column_stack([x.ravel(), np.zeros(x.size), z.ravel()])
    config = AnalyticsConfig(uncertainty_floor_m=0.001)
    b = preprocess(points, capture(), config)
    right = np.concatenate([points, points + [0, -0.06, 0]])
    result = detect_geometry(b, right, valid_registration(b.record), reference(), config)
    assert any(
        "multiple_depth_layers" in p.quality_flags or "excessive_local_roughness" in p.quality_flags
        for p in result.patches
    )


def record(sensor, kind, value, t, received_delay=0.02):
    return SensorObservation(
        observation_id=f"{sensor}-{t}",
        sensor_id=sensor,
        asset_id="BW-01",
        acquired_at=NOW + timedelta(seconds=t),
        received_at=NOW + timedelta(seconds=t + received_delay),
        measurement_type=kind,
        value=float(value),
        unit="1" if kind == "operating_load" else "Pa",
        quality="good",
        provenance_id="fixture",
        location_reference="fixture",
    )


def public_dataset(path, rows):
    folder = path / "observations/iot"
    folder.mkdir(parents=True)
    (folder / "readings.jsonl").write_text("".join(r.model_dump_json() + "\n" for r in rows))
    manifest = ObservationManifest(
        manifest_id=path.name,
        run_id=path.name,
        dataset=DatasetProvenance(
            dataset_id=path.name, source_type="synthetic", description="controlled unit fixture"
        ),
        software_version="test",
        configuration_version="v1",
        master_seed=1,
        acquisition_namespace=path.name,
        observations=[
            ObservationReference(
                observation_id="stream",
                record_uri="observations/iot/readings.jsonl",
                kind="SensorObservation",
            )
        ],
        artifacts=[],
    )
    (path / "manifest.json").write_text(manifest.model_dump_json())


def sequence(seed=0, ramp=True):
    rng = np.random.default_rng(seed)
    rows = []
    filtered = 0.5
    previous = 0.5
    for t in range(0, 121, 2):
        load = 0.3 + 0.5 * t / 120 if ramp else 0.5
        if t == 0:
            filtered = load
        else:
            filtered = previous + (filtered - previous) * np.exp(-2 / 20)
        rows.extend(
            [
                record("load", "operating_load", load, t, 0.01),
                record("pressure", "pressure", 500000 + 600000 * filtered + rng.normal(0, 80), t),
            ]
        )
        previous = load
    return rows


def test_causal_models_calibration_and_out_of_range(tmp_path):
    paths = []
    for seed in range(6):
        path = tmp_path / f"healthy-{seed}"
        public_dataset(path, sequence(seed, seed % 3 != 0))
        paths.append(path)
    config = AnalyticsConfig()
    model = calibrate_operating(paths, config)
    assert model["sensors"]["pressure"]["tau_s"] == 20
    rows = sequence(80)
    conditioned = infer_operating(rows, model, config, "conditioned_quality")
    static = infer_operating(rows, model, config, "static")
    assert sum(bool(r.significant) for r in conditioned) < sum(bool(r.significant) for r in static)
    assert all(r.model_id == model["model_id"] for r in conditioned)
    target = record("pressure", "pressure", 800000, 10)
    past = record("load", "operating_load", 0.5, 8)
    future = record("load", "operating_load", 0.9, 12)
    delayed = record("load", "operating_load", 0.2, 9, 100)
    assert causal_load(target, [past, future, delayed], 0, 6) == 0.5
    unsupported = [
        record("load", "operating_load", 1, 0, 0.01),
        record("pressure", "pressure", 1100000, 0),
    ]
    assert infer_operating(unsupported, model, config)[0].status == "out_of_reference_range"
    assert infer_operating([target], model, config)[0].status == "inconclusive"


def test_saturation_quantitative_mask_and_legacy_conservatism():
    record = capture()
    arrays = {
        "temperature_c": np.array([[50.0, 80.0, np.nan]]),
        "valid_mask": np.array([[True, True, False]]),
        "saturation_mask": np.array([[False, True, False]]),
    }
    valid, saturated, known = quantitative_mask(arrays, record)
    assert known and valid.tolist() == [[True, False, False]]
    assert saturated.tolist() == [[False, True, False]]
    del arrays["saturation_mask"]
    assert not quantitative_mask(arrays, record)[0].any()
