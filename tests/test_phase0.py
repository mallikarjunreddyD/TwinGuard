import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys
import numpy as np
import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError
from twinguard import SCHEMA_VERSION
from twinguard.api.app import app
from twinguard.cli import main
from twinguard.core.contracts import (
    Asset,
    SensorObservation,
    ConditionAssessment,
    DatasetProvenance,
    ScenarioDefinition,
    InspectionCapture,
    PlantState,
    GeometricDetection,
    EvidenceRecord,
)
from twinguard.core.config import load_scenario
from twinguard.core.registry import ALL_MODELS, RESTRICTED_MODELS, export_schemas
from twinguard.core.serialization import analytics_json, write_ground_truth, write_observation
from twinguard.core.spatial import Frame, Transform
from twinguard.core.time import observation_age, is_fresh, simulated_time
from twinguard.evaluation.contracts import (
    FaultInjection,
    ExperimentDefinition,
    ExperimentRun,
    artifact_path,
)

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def fixture():
    return json.loads((ROOT / "datasets/synthetic/observation.json").read_text())


def fault():
    return FaultInjection.model_validate(
        yaml.safe_load((ROOT / "datasets/ground_truth/fault-S2.yaml").read_text())
    )


def transform(matrix=None, source="a", target="b"):
    return Transform(
        source=Frame(kind="world", reference_id=source),
        target=Frame(kind="world", reference_id=target),
        matrix=np.eye(4).tolist() if matrix is None else matrix,
    )


def test_asset():
    record = yaml.safe_load((ROOT / "configs/assets.yaml").read_text())[0]
    asset = Asset.model_validate(record)
    assert asset.asset_id == "wall-01"
    record["pose"]["source"]["reference_id"] = "wrong"
    with pytest.raises(ValidationError):
        Asset.model_validate(record)


@pytest.mark.parametrize(
    "field,value",
    [
        ("unit", "kelvin"),
        ("unit", "Pa"),
        ("value", "malformed"),
        ("value", "80"),
        ("value", True),
        ("value", float("nan")),
        ("value", -274),
        ("observation_id", ""),
        ("sensor_id", None),
        ("acquired_at", "2026-01-01T00:00:00"),
        ("acquired_at", "2026-01-01T00:00:00+01:00"),
        ("received_at", "2025-01-01T00:00:00Z"),
        ("processed_at", "2025-01-01T00:00:00Z"),
        ("sequence_number", -1),
        ("fault_label", "healthy"),
    ],
)
def test_bad_observation(field, value):
    data = fixture()
    data[field] = value
    with pytest.raises(ValidationError):
        SensorObservation.model_validate(data)


@pytest.mark.parametrize(
    "kind,value,unit",
    [
        ("pressure", -1, "Pa"),
        ("operating_load", 2, "1"),
        ("vector", [], "m"),
        ("temperature", [1, 2], "degC"),
    ],
)
def test_measurement_shape_and_range(kind, value, unit):
    with pytest.raises(ValidationError):
        SensorObservation.model_validate(
            fixture() | dict(measurement_type=kind, value=value, unit=unit)
        )


def test_unknown_not_healthy():
    assessment = ConditionAssessment(
        assessment_id="a",
        asset_id="wall-01",
        assessed_at=NOW,
        severity="unknown",
        confidence_status="insufficient",
        supporting_evidence_ids=[],
        missing_or_invalid_evidence_ids=["missing"],
        recommended_action="Human review",
        policy_id="policy",
        policy_version="v1",
        human_review="pending",
    )
    assert assessment.severity != "green"


def test_frames():
    with pytest.raises(ValidationError):
        Frame(kind="camera", reference_id="camera")
    with pytest.raises(ValidationError):
        Frame(kind="world", reference_id="")


def test_transforms():
    points = [[1, 2, 3]]
    identity = transform()
    assert identity.apply(points, identity.source) == points
    translation = np.eye(4)
    translation[:3, 3] = [4, 5, 6]
    t = transform(translation.tolist(), source="b", target="c")
    rotation = np.eye(4)
    rotation[:2, :2] = [[0, -1], [1, 0]]
    r = transform(rotation.tolist())
    assert r.apply(points, r.source) == [[-2, 1, 3]]
    assert t.apply(points, t.source) == [[5, 7, 9]]
    composed = t.compose(r)
    assert composed.apply(points, r.source) == [[2, 6, 9]]
    assert np.allclose(composed.inverse().apply([[2, 6, 9]], composed.target), points)
    with pytest.raises(ValueError):
        r.compose(t)
    with pytest.raises(ValueError):
        r.apply(points, t.target)


@pytest.mark.parametrize(
    "matrix",
    [
        np.eye(3).tolist(),
        [[1, 0, 0, 0]] * 4,
        np.diag([-1, 1, 1, 1]).tolist(),
        np.diag([2, 1, 1, 1]).tolist(),
        np.diag([1, 1, 1, 2]).tolist(),
        np.full((4, 4), np.nan).tolist(),
    ],
)
def test_invalid_transforms(matrix):
    with pytest.raises(ValidationError):
        transform(matrix)


def test_time_and_delivery():
    record = SensorObservation.model_validate(
        fixture() | {"delivery_status": "out_of_order", "sequence_number": 2}
    )
    assert "Z" in record.model_dump_json()
    assert record.delivery_status == "out_of_order"
    assert observation_age(record.acquired_at, record.received_at) == 1
    assert is_fresh(record.acquired_at, record.received_at, 2)
    assert not is_fresh(record.acquired_at, record.received_at, 0.5)
    assert simulated_time(NOW, 3, 2) == NOW + timedelta(seconds=6)
    assert simulated_time(NOW, 3, 2) == simulated_time(NOW, 3, 2)
    with pytest.raises(ValueError):
        observation_age(datetime(2026, 1, 1), NOW)


@pytest.mark.parametrize("path", sorted((ROOT / "scenarios").glob("*.yaml")))
def test_scenarios(path):
    scenario = load_scenario(path, ROOT)
    assert ScenarioDefinition.model_validate_json(scenario.model_dump_json()) == scenario
    assert scenario.random_seed == 42 + int(scenario.scenario_id[1:])


@pytest.mark.parametrize(
    "change",
    [
        {"duration_s": 0},
        {"time_step_s": -1},
        {"duration_s": 0.5},
        {"asset_ids": ["missing"]},
        {"sensor_config_ids": ["missing"]},
    ],
)
def test_invalid_scenario(tmp_path, change):
    raw = yaml.safe_load((ROOT / "scenarios/S0.yaml").read_text()) | change
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises((ValidationError, ValueError)):
        load_scenario(path, ROOT)


def test_fault_asset_reference(tmp_path):
    import shutil

    shutil.copytree(ROOT / "configs", tmp_path / "configs")
    (tmp_path / "datasets/ground_truth").mkdir(parents=True)
    data = fault().model_dump(mode="json") | {"asset_id": "missing"}
    (tmp_path / "datasets/ground_truth/fault-S2.yaml").write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="missing"):
        load_scenario(ROOT / "scenarios/S2.yaml", tmp_path)


def test_isolation(tmp_path):
    record = SensorObservation.model_validate(fixture())
    public = json.loads(analytics_json(record))
    assert not set(public) & set(fault().model_dump()) - {"schema_version", "asset_id"}
    for field in (
        "fault_id",
        "true_displacement_m",
        "severity_parameters",
        "fault_config_references",
    ):
        with pytest.raises(ValidationError):
            SensorObservation.model_validate(fixture() | {field: "secret"})
    with pytest.raises(TypeError):
        analytics_json(fault())
    with pytest.raises(ValidationError):
        SensorObservation.model_validate(fault().model_dump())
    private_path = write_ground_truth(fault(), tmp_path)
    public_path = tmp_path / "observation.json"
    write_observation(record, public_path)
    assert "datasets/ground_truth" in str(private_path)
    assert private_path.stat().st_mode & 0o777 == 0o600
    assert "true_displacement" not in public_path.read_text()
    assert (
        not {"fault_id", "fault_label", "true_displacement_m", "severity_parameters"}
        & SensorObservation.model_json_schema()["properties"].keys()
    )


def test_schemas(tmp_path):
    export_schemas(tmp_path)
    for name, model in ALL_MODELS.items():
        path = (
            tmp_path / ("restricted/" if name in RESTRICTED_MODELS else "") / f"{name}.schema.json"
        )
        schema = json.loads(path.read_text())
        assert schema == model.model_json_schema()
        assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
        assert schema["additionalProperties"] is False
        committed = ROOT / "schemas" / path.relative_to(tmp_path)
        assert json.loads(committed.read_text()) == schema


def test_hybrid_provenance():
    with pytest.raises(ValidationError):
        DatasetProvenance(dataset_id="hybrid", source_type="hybrid", description="missing lineage")
    for path in (ROOT / "datasets").glob("*/manifest.json"):
        DatasetProvenance.model_validate_json(path.read_text())


def test_experiments():
    for path in (ROOT / "experiments").glob("E*.yaml"):
        assert ExperimentDefinition.model_validate(
            yaml.safe_load(path.read_text())
        ).implementation_status == (
            "implemented" if path.stem in ("E1", "E2") else "not_implemented"
        )
    assert artifact_path("E1", "run-01", "cloud") == "experiments/outputs/E1/run-01/cloud"
    with pytest.raises(ValidationError):
        artifact_path("../escape", "run", "cloud")


def test_api():
    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/version").json()["schema_version"] == SCHEMA_VERSION
    capability = client.get("/capabilities").json()
    assert "registration" in capability["implemented"]
    assert "evidence_fusion" in capability["pending"]
    assert "evidence_fusion" not in capability["implemented"]
    assert client.post("/analyze").status_code == 404


def test_cli(tmp_path, capsys):
    assert main(["--root", str(ROOT), "doctor"]) == 0
    assert main(["--root", str(tmp_path), "doctor"]) == 1
    assert main(["--root", str(ROOT), "validate-config", str(ROOT / "scenarios/S0.yaml")]) == 0
    invalid = tmp_path / "bad.yaml"
    invalid.write_text("duration_s: -1")
    assert main(["--root", str(ROOT), "validate-config", str(invalid)]) == 1
    assert "Validation failed" in capsys.readouterr().err
    result = subprocess.run(
        [sys.executable, "-m", "twinguard.cli", "validate-config", str(invalid)],
        cwd=ROOT,
        capture_output=True,
    )
    assert result.returncode == 1
    assert (
        main(
            [
                "validate-data",
                str(ROOT / "datasets/synthetic/observation.json"),
                "--kind",
                "SensorObservation",
            ]
        )
        == 0
    )


def test_future_contracts_roundtrip():
    state = PlantState(
        state_id="state",
        timestamp=NOW,
        plant_id="plant",
        operating_mode="steady_operation",
        normalized_load=0.5,
        process_pressure_pa=1000,
        process_temperature_c=80,
        ambient_temperature_c=25,
    )
    detection = GeometricDetection(
        detection_id="d",
        asset_id="wall-01",
        baseline_capture_id="b",
        current_capture_id="c",
        region_id="r",
        displacement_m=0.01,
        displacement_uncertainty_m=0.002,
        quality_status="partial",
        algorithm_id="pending",
        algorithm_version="v1",
        detected_at=NOW,
    )
    evidence = EvidenceRecord(
        evidence_id="e",
        asset_id="wall-01",
        source_id="d",
        modality="geometric",
        acquired_at=NOW,
        processed_at=NOW,
        hypothesis_id="deformation",
        quality="unknown",
        operating_context_id="state",
        validity="inconclusive",
        provenance_id="fixture",
    )
    pose = Transform(
        source=Frame(kind="sensor_local", reference_id="lidar"),
        target=Frame(kind="world", reference_id="plant"),
        matrix=np.eye(4).tolist(),
    )
    capture = InspectionCapture(
        capture_id="c",
        mission_id="m",
        asset_ids=["wall-01"],
        sensor_id="lidar",
        acquired_at=NOW,
        received_at=NOW,
        modality="lidar",
        artifact={
            "artifact_id": "cloud",
            "uri": "pending.pcd",
            "media_type": "application/octet-stream",
        },
        coordinate_frame=pose.target,
        sensor_pose=pose,
        calibration_id="cal",
        provenance_id="fixture",
    )
    run = ExperimentRun(
        experiment_id="E1",
        run_id="run",
        scenario_id="S0",
        dataset_id="fixture",
        dataset_provenance_reference="fixture",
        dataset_source_type="synthetic",
        random_seed=42,
        software_version="0.1.0",
        configuration_version="v1",
        algorithm_references=[],
        configuration_references=["S0"],
        started_at=NOW,
        outputs=[],
        evaluation_status="not_implemented",
        metric_artifacts=[],
    )
    for record in (state, detection, evidence, capture, run):
        assert type(record).model_validate_json(record.model_dump_json()) == record
    assert "fault" not in analytics_json(capture)
    with pytest.raises(ValidationError):
        GeometricDetection.model_validate(detection.model_dump() | {"confidence": 0.9})


def test_nested_leakage_and_invalid_yaml(tmp_path):
    from twinguard.core.contracts import Artifact

    with pytest.raises(ValidationError):
        Artifact(
            artifact_id="a",
            uri="file.pcd",
            media_type="application/octet-stream",
            true_fault="secret",
        )
    path = tmp_path / "broken.yaml"
    path.write_text("key: [unterminated")
    assert main(["--root", str(ROOT), "validate-config", str(path)]) == 1


def test_no_restricted_imports_in_consumers():
    import ast

    for module in ("analytics", "fusion", "inspection", "api"):
        for path in (ROOT / "src/twinguard" / module).rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    assert not (node.module or "").startswith(
                        ("twinguard.evaluation", "twinguard.plant", "twinguard.core.config")
                    )
                elif isinstance(node, ast.Import):
                    assert all(
                        not alias.name.startswith(("twinguard.evaluation", "twinguard.plant"))
                        for alias in node.names
                    )


def test_schema_version_and_missing_id():
    data = fixture()
    del data["observation_id"]
    with pytest.raises(ValidationError):
        SensorObservation.model_validate(data)
    with pytest.raises(ValidationError):
        SensorObservation.model_validate(fixture() | {"schema_version": "2.0.0"})


def test_out_of_order_acquisitions_remain_valid():
    later = SensorObservation.model_validate(fixture() | {"sequence_number": 2})
    earlier = SensorObservation.model_validate(
        fixture()
        | {
            "observation_id": "obs-earlier",
            "sequence_number": 1,
            "acquired_at": "2025-12-31T23:59:59Z",
            "received_at": "2026-01-01T00:00:02Z",
            "delivery_status": "out_of_order",
        }
    )
    assert earlier.acquired_at < later.acquired_at
    assert earlier.received_at > later.received_at
    assert earlier.sequence_number < later.sequence_number


def test_restricted_writer_revalidates_ids(tmp_path):
    invalid = fault().model_copy(update={"fault_id": "../escape"})
    with pytest.raises(ValidationError):
        write_ground_truth(invalid, tmp_path)
    assert not (tmp_path / "datasets").exists()
