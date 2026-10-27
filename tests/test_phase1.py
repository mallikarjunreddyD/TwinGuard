"""Numerical and geometric verification of Phase 1 (no sensing/analytics)."""

from datetime import timedelta
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
import pytest
import trimesh
from pydantic import ValidationError
from twinguard.cli import main
from twinguard.core.boundaries import audit_consumers, forbidden_imports
from twinguard.core.contracts import SensorConfiguration, OperatingPoint
from twinguard.core.serialization import analytics_json
from twinguard.evaluation.contracts import ExperimentDefinition, FaultInjection, GroundTruthSnapshot
from twinguard.plant.config import load_plant_config, PlantConfig
from twinguard.plant.model import create_baseline_plant
from twinguard.plant.simulator import PlantSimulator
from twinguard.plant.io import simulator_from_scenario, export_run, load_run
from twinguard.plant.contracts import SimulationManifest
from twinguard.plant.geometry import validate_mesh
from twinguard.plant.faults import spatial_weights

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {"BW-01", "DR-01", "SP-01", "SP-02", "SUP-01", "VL-01", "REF-01"}


@pytest.fixture(scope="module")
def plant():
    return create_baseline_plant(load_plant_config(ROOT / "configs/plant.yaml"), 42)


@pytest.fixture
def s0():
    return simulator_from_scenario(ROOT / "scenarios/S0.yaml", ROOT)


def injected(sim, category, asset_id="BW-01", **changes):
    data = dict(
        fault_id="test-fault",
        asset_id=asset_id,
        category=category,
        start_at=sim.scenario.simulation_start + timedelta(seconds=30),
        end_at=sim.scenario.simulation_start + timedelta(seconds=90),
        severity_parameters={},
        affected_region_id="surface",
        ground_truth_artifacts=[],
    )
    data.update(changes)
    return FaultInjection.model_validate(data)


def test_baseline_geometry(plant):
    assert set(plant.asset_registry) == REQUIRED
    assert np.allclose(plant.mesh("BW-01").extents, [1.89, 0.13, 2.4])
    assert np.allclose(plant.mesh("DR-01").extents, [2.1, 0.64, 0.64])
    for aid in REQUIRED:
        mesh = plant.mesh(aid)
        validate_mesh(mesh)
        assert mesh.is_watertight
        assert mesh.area_faces.min() > 1e-14
        pose = plant.world_pose(aid)
        expected = np.asarray(pose.matrix)[:3, 3]
        assert np.allclose(pose.apply([[0, 0, 0]], pose.source)[0], expected)
        world = pose.apply(mesh.vertices[:8].tolist(), pose.source)
        assert np.allclose(pose.inverse().apply(world, pose.target), mesh.vertices[:8])
    parent = plant.world_pose("SP-01")
    relative = plant.asset_registry["VL-01"].pose
    assert np.allclose(parent.compose(relative).matrix, plant.world_pose("VL-01").matrix)
    assert plant.asset_registry["VL-01"].parent_asset_id == "SP-01"


def test_baseline_defensive_copies(plant, s0):
    before = plant.mesh("BW-01").vertices.copy()
    mesh = plant.mesh("BW-01")
    mesh.vertices += 9
    config = plant.config
    config.assets[0].origin_m = (9, 9, 9)
    assets = plant.asset_registry
    assets["BW-01"].name = "modified"
    assert np.array_equal(plant.mesh("BW-01").vertices, before)
    assert plant.config.assets[0].origin_m != (9, 9, 9)
    assert plant.asset_registry["BW-01"].name == "BW-01"


@pytest.mark.parametrize("name", ["S0", "S1", "S2", "S3", "S4", "S5"])
def test_all_scenarios_execute(name):
    sim = simulator_from_scenario(ROOT / f"scenarios/{name}.yaml", ROOT)
    for t in [0, 45, 60, 120]:
        state = sim.state_at(t)
        assert state.operating.process_pressure_pa >= 0
        assert state.operating.timestamp == sim.scenario.simulation_start + timedelta(seconds=t)
        assert set(state.assets) == REQUIRED
    if name in ("S0", "S1"):
        assert sim.ground_truth_at(60).fault_states == []


def test_load_response_expansion(s0):
    sim = simulator_from_scenario(ROOT / "scenarios/S1.yaml", ROOT)
    initial = sim.state_at(0)
    current = sim.state_at(60)
    assert current.operating.normalized_load > initial.operating.normalized_load
    assert 180 < current.operating.process_temperature_c < 210
    assert 800000 < current.operating.process_pressure_pa < 980000
    wall = current.assets["BW-01"]
    reference = sim.baseline.mesh("BW-01").vertices
    expected = 12e-6 * 2.4 * (current.operating.process_temperature_c - 180)
    assert wall.normal_expansion_m == pytest.approx(expected, abs=1e-12)
    assert np.ptp(wall.vertices_local_m[:, 2]) - 2.4 == pytest.approx(expected, abs=1e-12)
    assert np.array_equal(wall.vertices_local_m[:, :2], reference[:, :2])
    assert s0.state_at(120).operating.process_temperature_c == pytest.approx(180)
    assert s0.state_at(120).operating.process_pressure_pa == pytest.approx(800000)


@pytest.mark.parametrize("profile", ["decrease", "startup"])
def test_other_operating_profiles(s0, profile):
    scenario = s0.scenario.model_copy(deep=True)
    if profile == "decrease":
        scenario.operating_profile = [
            OperatingPoint(offset_s=0, normalized_load=0.8, operating_mode="load_transition"),
            OperatingPoint(offset_s=60, normalized_load=0.3),
        ]
    else:
        scenario.operating_profile = [
            OperatingPoint(offset_s=0, normalized_load=0, operating_mode="shutdown"),
            OperatingPoint(offset_s=60, normalized_load=0.5, operating_mode="startup"),
        ]
    sim = PlantSimulator(s0.baseline, scenario, [])
    first, last = sim.operating_at(0), sim.operating_at(120)
    if profile == "decrease":
        assert last.process_temperature_c < first.process_temperature_c
    else:
        assert last.process_temperature_c > first.process_temperature_c
    assert last.process_pressure_pa >= 0


@pytest.mark.parametrize("tau", [0.001, 1, 1000])
def test_stable_dynamics(s0, tau):
    config = s0.baseline.config
    config.dynamics.temperature_tau_s = tau
    config.dynamics.pressure_tau_s = tau
    scenario = s0.scenario.model_copy(deep=True)
    scenario.operating_profile = [
        OperatingPoint(offset_s=0, normalized_load=0),
        OperatingPoint(offset_s=60, normalized_load=1),
    ]
    sim = PlantSimulator(create_baseline_plant(config), scenario, [])
    for t in [0, 0.3, 30, 59.9, 60, 119.99, 120]:
        op = sim.operating_at(t)
        assert 130 - 1e-8 <= op.process_temperature_c <= 230 + 1e-8
        assert 500000 - 1e-7 <= op.process_pressure_pa <= 1100000 + 1e-7


@pytest.mark.parametrize("amplitude", [0.01, 0.02, 0.03, 0.05])
def test_actual_mesh_deformation_and_isolation(s0, amplitude):
    fault = injected(s0, "localized_geometric_deformation", true_displacement_m=amplitude)
    sim = PlantSimulator(s0.baseline, s0.scenario, [fault])
    baseline = sim.baseline.mesh("BW-01").vertices.copy()
    before = sim.state_at(29).assets["BW-01"].vertices_local_m
    actual = sim.state_at(60).assets["BW-01"].vertices_local_m
    assert np.array_equal(before, baseline)
    delta = actual - baseline
    assert np.max(np.linalg.norm(delta, axis=1)) == pytest.approx(amplitude, abs=1e-10)
    outside = spatial_weights(baseline, fault) == 0
    assert np.array_equal(actual[outside], baseline[outside])
    assert np.array_equal(sim.baseline.mesh("BW-01").vertices, baseline)
    assert np.array_equal(sim.state_at(100).assets["BW-01"].vertices_local_m, actual)
    validate_mesh(
        trimesh.Trimesh(vertices=actual, faces=sim.baseline.mesh("BW-01").faces, process=False)
    )


def test_evolution_persistence_and_repair(s0):
    fault = injected(
        s0,
        "localized_geometric_deformation",
        true_displacement_m=0.03,
        evolution="linear",
        growth_duration_s=30,
        persistence="persistent",
    )
    sim = PlantSimulator(s0.baseline, s0.scenario, [fault])
    assert sim.ground_truth_at(30).fault_states[0].applied_peak_displacement_m == 0
    assert sim.ground_truth_at(45).fault_states[0].applied_peak_displacement_m == pytest.approx(
        0.015
    )
    assert sim.ground_truth_at(120).fault_states[0].applied_peak_displacement_m == pytest.approx(
        0.03
    )
    fault.repair_at = fault.start_at + timedelta(seconds=70)
    repaired = PlantSimulator(s0.baseline, s0.scenario, [fault])
    assert not repaired.ground_truth_at(100).fault_states[0].present
    assert np.array_equal(
        repaired.state_at(100).assets["BW-01"].vertices_local_m, s0.baseline.mesh("BW-01").vertices
    )


def test_support_translation(s0):
    shift = np.array([0.02, -0.01, 0.005])
    fault = injected(
        s0, "structural_support_displacement", asset_id="SUP-01", displacement_vector_m=tuple(shift)
    )
    sim = PlantSimulator(s0.baseline, s0.scenario, [fault])
    before = sim.state_at(0).assets["SUP-01"]
    after = sim.state_at(60).assets["SUP-01"]
    assert np.allclose(after.vertices_world_m - before.vertices_world_m, shift, atol=1e-12)
    assert np.allclose(
        np.asarray(after.world_pose.matrix)[:3, 3] - np.asarray(before.world_pose.matrix)[:3, 3],
        shift,
    )
    assert np.array_equal(
        sim.state_at(60).assets["DR-01"].vertices_world_m,
        s0.state_at(60).assets["DR-01"].vertices_world_m,
    )


def test_hotspot_field_recovery(s0):
    fault = injected(
        s0,
        "thermal_hotspot",
        true_process_deviation=12,
        deviation_unit="degC",
        persistence="recover",
        recovery_duration_s=20,
    )
    sim = PlantSimulator(s0.baseline, s0.scenario, [fault])
    base = s0.state_at(60).assets["BW-01"]
    current = sim.state_at(60).assets["BW-01"]
    assert np.max(current.surface_temperature_c - base.surface_temperature_c) == pytest.approx(12)
    outside = spatial_weights(s0.baseline.mesh("BW-01").vertices, fault) == 0
    assert np.array_equal(
        current.surface_temperature_c[outside], base.surface_temperature_c[outside]
    )
    assert np.array_equal(current.vertices_local_m, base.vertices_local_m)
    assert np.max(sim.state_at(100).assets["BW-01"].surface_temperature_c) - 180 == pytest.approx(6)
    assert np.max(sim.state_at(110).assets["BW-01"].surface_temperature_c) == pytest.approx(180)


@pytest.mark.parametrize(
    "variable,unit,delta", [("pressure_pa", "Pa", 200000), ("temperature_c", "degC", 12)]
)
def test_process_fault_changes_only_intended_state(s0, variable, unit, delta):
    fault = injected(
        s0,
        "abnormal_process_measurement",
        true_process_deviation=delta,
        deviation_unit=unit,
        process_variable=variable,
    )
    sim = PlantSimulator(s0.baseline, s0.scenario, [fault])
    state = sim.state_at(60)
    normal = s0.state_at(60)
    if variable == "pressure_pa":
        assert state.operating.process_pressure_pa - normal.operating.process_pressure_pa == delta
    else:
        assert (
            state.operating.process_temperature_c - normal.operating.process_temperature_c == delta
        )
    for aid in REQUIRED:
        assert np.array_equal(
            state.assets[aid].vertices_world_m, normal.assets[aid].vertices_world_m
        )
        assert np.array_equal(
            state.assets[aid].surface_temperature_c, normal.assets[aid].surface_temperature_c
        )
    assert sim.state_at(100).operating == normal.operating.model_copy(
        update={
            "state_id": sim.state_at(100).operating.state_id,
            "timestamp": sim.state_at(100).timestamp,
        }
    )


def test_multiple_faults_and_rejection(s0):
    a = injected(s0, "localized_geometric_deformation", true_displacement_m=0.02)
    b = injected(
        s0, "thermal_hotspot", fault_id="hot", true_process_deviation=12, deviation_unit="degC"
    )
    sim = PlantSimulator(s0.baseline, s0.scenario, [a, b])
    assert len(sim.ground_truth_at(60).fault_states) == 2
    assert sim.state_at(60).assets["BW-01"].surface_temperature_c.max() == 192
    p = injected(s0, "abnormal_process_measurement", target_value=900000)
    q = p.model_copy(update={"fault_id": "other"})
    with pytest.raises(ValueError, match="Incompatible"):
        PlantSimulator(s0.baseline, s0.scenario, [p, q])


def test_reproducibility_order_and_seeds(s0):
    sim = simulator_from_scenario(ROOT / "scenarios/S2.yaml", ROOT)
    first = sim.state_at(60)
    sim.state_at(100)
    sim.state_at(0)
    again = sim.state_at(60)
    for aid in REQUIRED:
        assert np.array_equal(
            first.assets[aid].vertices_world_m, again.assets[aid].vertices_world_m
        )
    other = simulator_from_scenario(ROOT / "scenarios/S2.yaml", ROOT)
    assert first.operating == other.state_at(60).operating
    scenario = s0.scenario.model_copy(update={"random_seed": 999})
    deterministic = PlantSimulator(s0.baseline, scenario, [])
    assert deterministic.operating_at(42) == s0.operating_at(42)
    config = s0.baseline.config
    config.dynamics.process_variation_c = 0.5
    first = PlantSimulator(create_baseline_plant(config), s0.scenario, [])
    second = PlantSimulator(create_baseline_plant(config), scenario, [])
    assert (
        first.operating_at(42).process_temperature_c
        != second.operating_at(42).process_temperature_c
    )
    assert first.operating_at(42) == first.operating_at(42)
    assert first.operating_at(42).process_pressure_pa == second.operating_at(42).process_pressure_pa


def test_exports_replay_and_checksums(tmp_path):
    sim = simulator_from_scenario(ROOT / "scenarios/S2.yaml", ROOT)
    output = tmp_path / "run-S2"
    manifest = export_run(sim, output, snapshot_times=[0, 60])
    parsed = SimulationManifest.model_validate(manifest)
    assert parsed.random_seed == sim.scenario.random_seed
    for artifact in parsed.artifacts:
        file = output / artifact.uri
        assert file.is_file()
        assert hashlib.sha256(file.read_bytes()).hexdigest() == artifact.sha256
    truth = json.loads((output / "restricted/ground_truth.json").read_text())
    assert GroundTruthSnapshot.model_validate(truth[1]).fault_states[
        0
    ].applied_peak_displacement_m == pytest.approx(0.03)
    assert (output / "restricted").stat().st_mode & 0o777 == 0o700
    reloaded = load_run(output)
    assert reloaded.scenario == sim.scenario
    assert np.array_equal(
        reloaded.state_at(60).assets["BW-01"].vertices_world_m,
        sim.state_at(60).assets["BW-01"].vertices_world_m,
    )
    ply = trimesh.load(output / "snapshots/t_60/BW-01.ply", process=False)
    assert np.allclose(ply.vertices, sim.state_at(60).assets["BW-01"].vertices_world_m, atol=2e-7)
    scene = trimesh.load(output / "snapshots/t_60/plant.glb", force="scene", process=False)
    assert set(scene.geometry) == REQUIRED
    expected = np.concatenate([a.vertices_world_m for a in sim.state_at(60).assets.values()])
    assert np.allclose(scene.bounds, [expected.min(0), expected.max(0)], atol=2e-7)
    with pytest.raises(ValueError, match="not empty"):
        export_run(sim, output)


def test_s2_and_historical_schedule():
    s2 = simulator_from_scenario(ROOT / "scenarios/S2.yaml", ROOT)
    assert [i.offset_s for i in s2.scenario.inspections if i.modality == "lidar"] == [0, 60]
    s5 = simulator_from_scenario(ROOT / "scenarios/S5.yaml", ROOT)
    assert s5.state_at(-3600).timestamp == s5.scenario.simulation_start - timedelta(hours=1)
    assert s5.operating_at(100).process_pressure_pa > s5.operating_at(0).process_pressure_pa


@pytest.mark.parametrize("time", [-1, 121, float("nan"), float("inf")])
def test_invalid_time(s0, time):
    with pytest.raises(ValueError):
        s0.state_at(time)


def test_read_boundary_and_recursive_imports(s0, tmp_path):
    reader = s0.sensing_reader()
    view = reader.read_at(60)
    assert not hasattr(view, "fault_states")
    assert not hasattr(view, "configuration")
    assert view.pressure_pa == s0.state_at(60).operating.process_pressure_pa
    with pytest.raises(TypeError):
        analytics_json(view)
    with pytest.raises(TypeError):
        analytics_json(s0.state_at(60))
    with pytest.raises(TypeError):
        analytics_json(s0.ground_truth_at(60))
    with pytest.raises(ValueError):
        view.surfaces[0].vertices_world_m[0, 0] = 1
    assert audit_consumers(ROOT / "src/twinguard") == []
    path = tmp_path / "nested.py"
    for statement in [
        "from twinguard.evaluation.private import truth",
        "from twinguard import evaluation",
        "from ...evaluation.contracts import FaultInjection",
        "import twinguard.plant.simulator",
        "from twinguard.sensing.read import PhysicalReadView",
    ]:
        path.write_text(statement)
        assert forbidden_imports(path, "twinguard.analytics.deep.nested")


def test_sensor_and_experiment_compatibility():
    import yaml

    for raw in yaml.safe_load((ROOT / "configs/sensors.yaml").read_text()):
        SensorConfiguration.model_validate(raw)
    for status in ["not_implemented", "in_progress", "implemented", "validated"]:
        record = ExperimentDefinition(
            experiment_id="E1",
            version="v1",
            inputs=[],
            outputs=[],
            planned_metrics=[],
            baseline="pending",
            implementation_status=status,
        )
        assert record.implementation_status == status


def test_cli_simulation_and_errors(tmp_path):
    output = tmp_path / "cli-run"
    assert (
        main(
            [
                "--root",
                str(ROOT),
                "plant",
                "simulate",
                "--scenario",
                str(ROOT / "scenarios/S0.yaml"),
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )
    assert main(["plant", "inspect", "--run-dir", str(output)]) == 0
    assert (
        main(["plant", "snapshot", "--run-dir", str(output), "--time", "12.5", "--format", "ply"])
        == 0
    )
    assert (output / "snapshots/t_12p5/BW-01.ply").exists()
    assert main(["plant", "snapshot", "--run-dir", str(output), "--time", "999"]) == 1
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "twinguard.cli",
            "plant",
            "build",
            "--config",
            "absent.yaml",
            "--output-dir",
            str(tmp_path / "bad"),
        ],
        capture_output=True,
        cwd=ROOT,
    )
    assert result.returncode == 1


def test_invalid_plant_config(plant):
    raw = plant.config.model_dump()
    raw["assets"][0]["dimensions_m"]["height"] = -1
    with pytest.raises(ValidationError):
        PlantConfig.model_validate(raw)
    raw = plant.config.model_dump()
    raw["assets"][0]["parent_asset_id"] = "BW-01"
    with pytest.raises(ValidationError):
        PlantConfig.model_validate(raw)


def test_headless_visualization(s0, tmp_path):
    pytest.importorskip("matplotlib")
    from twinguard.plant.visualize import render

    path = render(s0.state_at(60), tmp_path / "view.png", s0.baseline)
    assert path.read_bytes().startswith(b"\x89PNG")
    from PIL import Image

    with Image.open(path) as image:
        assert image.width >= 1000 and image.height >= 800
        assert np.asarray(image).std() > 10


@pytest.mark.parametrize("name", ["P0", "P1", "P2", "P3", "P4"])
def test_profile_configuration_examples(name):
    sim = simulator_from_scenario(ROOT / f"configs/profiles/{name}.yaml", ROOT)
    assert np.isfinite(sim.operating_at(60).process_temperature_c)
    if name == "P2":
        assert (
            sim.operating_at(120).process_temperature_c < sim.operating_at(0).process_temperature_c
        )
    if name == "P3":
        assert (
            sim.operating_at(120).process_temperature_c > sim.operating_at(0).process_temperature_c
        )


def test_checksum_tampering_detected(s0, tmp_path):
    from twinguard.plant.io import verify_run

    output = tmp_path / "integrity-run"
    export_run(s0, output, snapshot_times=[0])
    (output / "plant_config.json").write_text("{}")
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_run(output)


def test_nested_package_relative_import_audit(tmp_path):
    path = tmp_path / "analytics/deep/__init__.py"
    path.parent.mkdir(parents=True)
    path.write_text("from ...evaluation.contracts import FaultInjection")
    assert audit_consumers(tmp_path)


def test_faults_require_consistent_physical_parameters(s0):
    with pytest.raises(ValueError, match="magnitude"):
        PlantSimulator(s0.baseline, s0.scenario, [injected(s0, "thermal_hotspot")])
    conflict = injected(
        s0,
        "localized_geometric_deformation",
        true_displacement_m=0.03,
        severity_parameters={"amplitude_m": 0.05},
    )
    with pytest.raises(ValueError, match="Conflicting"):
        PlantSimulator(s0.baseline, s0.scenario, [conflict])


def test_configurable_sensor_pose(s0):
    from twinguard.core.spatial import Frame, Transform

    frame = Frame(kind="sensor_local", reference_id="lidar-01")
    pose = Transform(
        source=frame,
        target=Frame(kind="asset_local", reference_id="BW-01"),
        matrix=np.eye(4).tolist(),
    )
    sensor = SensorConfiguration(
        sensor_id="lidar-01",
        asset_id="BW-01",
        source_type="synthetic",
        configuration_version="v2",
        description="Phase 2 configuration only",
        modality="lidar",
        coordinate_frame=frame,
        pose=pose,
        acquisition_parameters={"vertical_fov_rad": 1.0},
        calibration_reference="cal-v1",
        noise_model_reference="pending",
        measurement_configuration={"range_m": 5.0},
    )
    assert SensorConfiguration.model_validate_json(sensor.model_dump_json()) == sensor
    assert s0.sensing_reader().read_at(0).coordinate_frame.reference_id == "plant-01"


def test_phase0_documentation_still_tracked():
    result = subprocess.run(
        ["git", "ls-files", "docs"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    tracked = set(result.stdout.splitlines())
    for name in (
        "ARCHITECTURE",
        "DATA_CONTRACTS",
        "SCENARIOS",
        "EXPERIMENTS",
        "TRL_EVIDENCE",
        "PHASES",
        "ASSUMPTIONS_AND_LIMITATIONS",
    ):
        assert f"docs/{name}.md" in tracked


def test_snapshot_times_have_full_precision_names(s0):
    from twinguard.plant.io import time_name

    assert time_name(12.345671) != time_name(12.345672)
    assert time_name(60) == "t_60"
    assert s0.operating_at(12.345671).state_id != s0.operating_at(12.345672).state_id


def test_artifact_ids_stable_when_snapshots_added(s0, tmp_path):
    from twinguard.plant.io import refresh_checksums

    output = tmp_path / "stable-artifacts"
    first = export_run(s0, output, snapshot_times=[0])
    ids = {item["uri"]: item["artifact_id"] for item in first["artifacts"]}
    (output / "AAA-extra.json").write_text("{}")
    second = refresh_checksums(output)
    assert all(
        ids[item["uri"]] == item["artifact_id"]
        for item in second["artifacts"]
        if item["uri"] in ids
    )
