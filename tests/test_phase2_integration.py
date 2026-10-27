import json
from pathlib import Path
import numpy as np
import pytest
from pydantic import ValidationError
from twinguard.core.contracts import InspectionCapture, SensorObservation
from twinguard.core.serialization import analytics_json
from twinguard.core.observations import (
    load_public_observations,
    load_capture_arrays,
    validate_import_manifest,
    public_path,
)
from twinguard.sensing.acquisition import load_installation, acquire
from twinguard.sensing.lidar import LidarSensor
from twinguard.sensing.thermal import ThermalSensor
from twinguard.sensing.noise import stream
from twinguard.plant.io import simulator_from_scenario
from twinguard.evaluation.sensing import validate_sensing_run
from twinguard.cli import main

ROOT = Path(__file__).resolve().parents[1]


def small_config(level="L1"):
    config = load_installation(ROOT / f"configs/sensing/{level}.yaml")
    config.lidar.channels = 8
    config.lidar.horizontal_samples = 60
    config.thermal.width = 32
    config.thermal.height = 24
    for sensor in config.iot:
        sensor.sampling_interval_s = 60
    return config


@pytest.mark.parametrize("name", ["S0", "S1", "S2", "S3", "S4", "S5"])
def test_scenarios_export_valid_coherent_observations(name, tmp_path):
    simulator = simulator_from_scenario(ROOT / f"scenarios/{name}.yaml", ROOT)
    before = simulator.baseline.mesh("BW-01").vertices.copy()
    output = tmp_path / name
    acquire(simulator.sensing_reader(), simulator.scenario, small_config(), output)
    manifest = validate_import_manifest(output)
    assert manifest.dataset.source_type == "synthetic"
    records = load_public_observations(output)
    assert any(isinstance(r, SensorObservation) for r in records)
    assert any(isinstance(r, InspectionCapture) and r.modality == "thermal" for r in records)
    for record in records:
        assert record.source_type == "synthetic"
        assert record.configuration_version == "v1"
        assert record.received_at >= record.acquired_at
        text = analytics_json(record)
        assert not any(
            key in text
            for key in (
                "true_pose",
                "triangle_ids",
                "fault_id",
                "reference_temperature_c",
                "noiseless",
                "true_displacement",
            )
        )
        if isinstance(record, InspectionCapture):
            arrays = load_capture_arrays(output, record)
            assert len(arrays) > 0
    if name == "S2":
        scans = [r for r in records if isinstance(r, InspectionCapture) and r.modality == "lidar"]
        assert sorted(
            (r.acquired_at - simulator.scenario.simulation_start).total_seconds() for r in scans
        ) == [0, 60]
        assert scans[0].sensor_pose != scans[1].sensor_pose
        assert all(len(load_capture_arrays(output, r)["points_m"]) > 20 for r in scans)
    if name == "S5":
        assert min(r.acquired_at for r in records) < simulator.scenario.simulation_start
    report = validate_sensing_run(output)
    assert all(row["valid_returns"] > 0 for row in report["lidar"].values())
    assert np.array_equal(simulator.baseline.mesh("BW-01").vertices, before)
    assert (output / "evaluation_private").stat().st_mode & 0o777 == 0o700
    assert not any("evaluation_private" in a.uri for a in manifest.artifacts)


def test_execution_order_and_replay_consistency(tmp_path):
    simulator = simulator_from_scenario(ROOT / "scenarios/S2.yaml", ROOT)
    config = small_config()
    a = tmp_path / "repeat-a"
    b = tmp_path / "repeat-b"
    acquire(
        simulator.sensing_reader(),
        simulator.scenario,
        config,
        a,
        execution_order=["lidar", "thermal"],
    )
    acquire(
        simulator.sensing_reader(),
        simulator.scenario,
        config,
        b,
        execution_order=["thermal", "lidar"],
    )
    first = sorted(
        load_public_observations(a),
        key=lambda r: getattr(r, "capture_id", getattr(r, "observation_id", "")),
    )
    second = sorted(
        load_public_observations(b),
        key=lambda r: getattr(r, "capture_id", getattr(r, "observation_id", "")),
    )
    assert first == second
    for left, right in zip(first, second):
        if isinstance(left, InspectionCapture):
            for key, value in load_capture_arrays(a, left).items():
                assert np.array_equal(value, load_capture_arrays(b, right)[key], equal_nan=True)


def test_public_loader_rejects_private_references_symlinks_and_extra_arrays(tmp_path):
    simulator = simulator_from_scenario(ROOT / "scenarios/S0.yaml", ROOT)
    output = tmp_path / "isolation"
    acquire(simulator.sensing_reader(), simulator.scenario, small_config(), output)
    for uri in (
        "evaluation_private/sensor_truth.json",
        "observations/../../secret.json",
        "/etc/passwd",
    ):
        with pytest.raises(ValueError):
            public_path(output, uri)
    link = output / "observations/private-link"
    link.symlink_to(output / "evaluation_private", target_is_directory=True)
    with pytest.raises(ValueError):
        public_path(output, "observations/private-link/sensor_truth.json")
    records = load_public_observations(output)
    scan = next(r for r in records if isinstance(r, InspectionCapture) and r.modality == "lidar")
    arrays = load_capture_arrays(output, scan)
    np.savez(output / scan.artifact.uri, **arrays, triangle_ids=np.zeros(len(arrays["points_m"])))
    with pytest.raises(ValueError, match="privileged"):
        load_capture_arrays(output, scan)
    with pytest.raises(ValueError, match="checksum"):
        validate_import_manifest(output)


@pytest.mark.parametrize(
    "key",
    [
        "true_pose",
        "fault_id",
        "triangle_ids",
        "reference_temperature_c",
        "expected_pressure",
        "noiseless_reference",
    ],
)
def test_public_nested_metadata_rejects_leakage(key):
    from test_phase2_geometry import config, view, plane, capture

    record = capture(LidarSensor(config()), view(plane())).observation
    with pytest.raises(ValidationError):
        InspectionCapture.model_validate(record.model_dump() | {"quality_indicators": {key: 1.0}})


def test_privileged_envelope_not_serializable():
    from test_phase2_geometry import config, view, plane, capture

    product = capture(LidarSensor(config()), view(plane()))
    with pytest.raises(TypeError):
        analytics_json(product)
    with pytest.raises(TypeError):
        analytics_json(product.evaluation_private)


def test_actual_plant_hotspot_visible_with_thermal_projection():
    nominal = simulator_from_scenario(ROOT / "scenarios/S0.yaml", ROOT)
    hotspot = simulator_from_scenario(ROOT / "scenarios/S3.yaml", ROOT)
    c = small_config("L0").thermal

    def frame(sim):
        return ThermalSensor(c).capture(
            sim.sensing_reader().read_at(60),
            "frame",
            "test",
            stream(1, "test", c.sensor_id, "frame"),
            stream(1, "test", c.sensor_id, "frame", "pose"),
        )

    a = frame(nominal)
    b = frame(hotspot)
    valid = a.arrays["valid_mask"] & b.arrays["valid_mask"]
    residual = (b.arrays["temperature_c"] - a.arrays["temperature_c"])[valid]
    assert residual.max() > 6
    assert residual.min() == pytest.approx(0, abs=1e-5)


def test_cli_and_public_ply_reload(tmp_path):
    output = tmp_path / "cli-lidar"
    assert (
        main(
            [
                "--root",
                str(ROOT),
                "sensing",
                "lidar",
                "--scenario",
                str(ROOT / "scenarios/S2.yaml"),
                "--time",
                "60",
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )
    assert main(["sensing", "validate", "--run-dir", str(output)]) == 0
    record = load_public_observations(output)[0]
    arrays = load_capture_arrays(output, record)
    ply = record.model_copy(
        update={
            "artifact": record.artifact.model_copy(
                update={"uri": record.artifact.uri.replace(".npz", ".ply")}
            )
        }
    )
    assert np.allclose(load_capture_arrays(output, ply)["points_m"], arrays["points_m"], atol=2e-5)
    assert (
        main(
            [
                "sensing",
                "lidar",
                "--scenario",
                str(ROOT / "scenarios/S2.yaml"),
                "--time",
                "999",
                "--output-dir",
                str(tmp_path / "bad"),
            ]
        )
        == 1
    )


def test_scenario_enabled_sensor_selection(tmp_path):
    simulator = simulator_from_scenario(ROOT / "scenarios/S0.yaml", ROOT)
    scenario = simulator.scenario.model_copy(update={"sensor_config_ids": ["pressure-01"]})
    output = tmp_path / "selected"
    acquire(simulator.sensing_reader(), scenario, small_config(), output, modality="iot")
    records = load_public_observations(output)
    assert {r.sensor_id for r in records} == {"pressure-01"}


def test_imported_manifest_requires_real_dataset_provenance(tmp_path):
    from twinguard.core.observations import ObservationManifest

    simulator = simulator_from_scenario(ROOT / "scenarios/S0.yaml", ROOT)
    output = tmp_path / "import"
    manifest = acquire(
        simulator.sensing_reader(), simulator.scenario, small_config(), output, modality="iot"
    )
    raw = manifest.model_dump(mode="json")
    raw["dataset"]["source_type"] = "public_real_world"
    with pytest.raises(ValidationError):
        ObservationManifest.model_validate(raw)
    raw["dataset"].update(license="CC-BY-4.0", source_uri="https://example.org/dataset")
    assert ObservationManifest.model_validate(raw).dataset.license == "CC-BY-4.0"


def test_evaluator_can_access_separate_plant_truth(tmp_path):
    from twinguard.evaluation.sensing import attach_plant_truth
    from twinguard.evaluation.contracts import GroundTruthSnapshot

    simulator = simulator_from_scenario(ROOT / "scenarios/S2.yaml", ROOT)
    output = tmp_path / "truth-access"
    acquire(simulator.sensing_reader(), simulator.scenario, small_config(), output)
    path = attach_plant_truth(output, simulator)
    payload = json.loads(path.read_text())
    states = [GroundTruthSnapshot.model_validate(r) for r in payload["ground_truth_snapshots"]]
    assert next(s for s in states if s.time_s == 60).fault_states[
        0
    ].applied_peak_displacement_m == pytest.approx(0.03)
    assert all("fault_states" not in analytics_json(r) for r in load_public_observations(output))
    with pytest.raises(ValueError):
        public_path(output, "evaluation_private/plant_truth.json")


def test_configuration_fingerprint_survives_default_serialization():
    from twinguard.sensing.config import AcquisitionConfig, MeasurementNoise
    from twinguard.sensing.export import dataset_identity

    config = small_config()
    config.lidar.noise = MeasurementNoise(sigma=0.003)
    roundtrip = AcquisitionConfig.model_validate_json(config.model_dump_json())
    assert dataset_identity("S2", 44, config) == dataset_identity("S2", 44, roundtrip)
