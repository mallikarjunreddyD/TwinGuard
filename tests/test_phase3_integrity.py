from pathlib import Path
import numpy as np
import pytest
from pydantic import ValidationError
from twinguard.analytics.config import AnalyticsConfig
from twinguard.analytics.pipeline import analyze_geometry
from twinguard.analytics.reference import load_reference
from twinguard.core.boundaries import audit_consumers
from twinguard.core.observations import load_public_observations, load_capture_arrays
from twinguard.core.contracts import InspectionCapture
from twinguard.evaluation.experiments import generate_case
from twinguard.evaluation.analytics import verify_seal, evaluate_e1, classification
from twinguard.evaluation.observability import deformation_audit
from twinguard.evaluation.contracts import ExperimentBenchmark
from twinguard.sensing.thermal import ThermalSensor
from test_phase2_geometry import config, capture, view, plane

ROOT = Path(__file__).resolve().parents[1]


def test_saturation_pixel_status_and_legacy_roundtrip():
    camera = config("thermal", width=9, height=9, emissivity=1, measurement_max_c=80)
    product = capture(ThermalSensor(camera), view(plane(5, 120)))
    assert product.arrays["saturation_mask"].all()
    assert (product.arrays["pixel_status"] == 3).all()
    assert product.arrays["valid_mask"].all()
    assert (product.arrays["temperature_c"] == 80).all()
    assert product.observation.acquisition_parameters["measurement_max_c"] == 80


def test_prediction_precedes_truth_and_private_files_are_never_read(monkeypatch, tmp_path):
    case = "integrity-test"
    data = tmp_path / "data"
    pairs = generate_case(ROOT, data, case, 815, "L1", 0.03)
    original_read = Path.read_text

    def public_only(path, *args, **kwargs):
        if "evaluation_private" in path.parts:
            raise AssertionError("analytics attempted private read")
        return original_read(path, *args, **kwargs)

    output = tmp_path / "prediction"
    reference = load_reference(ROOT / "configs/analytics/accepted_reference.json")
    with monkeypatch.context() as scope:
        scope.setattr(Path, "read_text", public_only)
        results = analyze_geometry(pairs[0], pairs[1], AnalyticsConfig(), reference, output)
        replay = analyze_geometry(
            pairs[0], pairs[1], AnalyticsConfig(), reference, tmp_path / "replay"
        )
    assert (output / "predictions_ready.json").exists()
    for label, (registration, geometry) in results.items():
        assert "SUP-01" in geometry.asset_statuses
        assert registration.registered_artifact is not None
        assert (output / registration.registered_artifact.uri).is_file()
        assert registration.registered_coordinate_frame.reference_id == "plant-01"
        assert registration.transform_convention == "T_baseline_current"
        np.testing.assert_allclose(
            registration.transform.matrix, replay[label][0].transform.matrix, atol=1e-7
        )
        np.testing.assert_allclose(
            [
                p.displacement_m if p.displacement_m is not None else np.nan
                for p in geometry.patches
            ],
            [
                p.displacement_m if p.displacement_m is not None else np.nan
                for p in replay[label][1].patches
            ],
            atol=1e-7,
            equal_nan=True,
        )
    metrics = evaluate_e1(
        data,
        output,
        {"case_id": case, "amplitude_m": 0.03, "fidelity": "L1", "viewpoint": "changed"},
    )
    assert all(r["positive"] for r in metrics)
    assert audit_consumers(ROOT / "src/twinguard") == []
    (output / "B3/geometry.json").write_text("{}")
    with pytest.raises(ValueError, match="modified"):
        verify_seal(output)


def test_actual_observability_and_hidden_roi_is_not_public(tmp_path):
    data = tmp_path / "observable"
    generate_case(ROOT, data, "visibility", 891, "L0", 0.03)
    audit = deformation_audit(data)
    assert len(audit["captures"]) == 2
    assert all(
        row["all_region_hit_rays"] >= row["valid_region_returns"] > 0 for row in audit["captures"]
    )
    assert audit["common_observed_cell_fraction"] > 0
    # Introduce a real opaque surface into the physical read view, not a label edit.
    from dataclasses import replace
    from twinguard.evaluation.experiments import setup_scenario
    from twinguard.plant.config import load_plant_config
    from twinguard.plant.model import create_baseline_plant
    from twinguard.plant.simulator import PlantSimulator
    from twinguard.sensing.read import Surface
    from twinguard.sensing.acquisition import acquire, load_installation
    from twinguard.evaluation.sensing import attach_plant_truth
    from twinguard.core.contracts import InspectionSchedule

    scenario, faults = setup_scenario(ROOT, "occluded", 891, kind="geometric")
    scenario.sensor_config_ids = ["lidar-01"]
    scenario.inspections = [
        InspectionSchedule(sensor_id="lidar-01", offset_s=t, modality="lidar") for t in [0, 60]
    ]
    simulator = PlantSimulator(
        create_baseline_plant(load_plant_config(ROOT / "configs/plant.yaml")), scenario, faults
    )
    base_reader = simulator.sensing_reader()
    screen = Surface(
        "opaque-screen",
        np.array([[-1, 0.5, 0.2], [1, 0.5, 0.2], [1, 0.5, 2.9], [-1, 0.5, 2.9]]),
        np.array([[0, 1, 2], [0, 2, 3]]),
        np.full(4, 25.0),
    )

    class ScreenReader:
        def read_at(self, t):
            physical = base_reader.read_at(t)
            return replace(physical, surfaces=physical.surfaces + (screen,))

    data = tmp_path / "actually-occluded"
    acquire(ScreenReader(), scenario, load_installation(ROOT / "configs/sensing/L0.yaml"), data)
    attach_plant_truth(data, simulator)
    records = [r for r in load_public_observations(data) if isinstance(r, InspectionCapture)]
    hidden = deformation_audit(data)
    assert not hidden["pair_observable"]
    assert all(row["valid_region_returns"] == 0 for row in hidden["captures"])
    for record in records:
        assert "roi" not in record.model_dump()
        assert set(load_capture_arrays(data, record)) == {"points_m", "valid_returns"}


def test_calibration_seed_overlap_is_rejected():
    with pytest.raises(ValidationError):
        ExperimentBenchmark(
            benchmark_id="bad",
            experiment_id="E1",
            analytics_config="a",
            accepted_reference="r",
            calibration_seeds=[1, 2],
            evaluation_seeds=[2, 3],
        )


def test_trial_accounting_retains_inconclusive_positive_cases():
    metrics = classification(
        [
            {"positive": True, "detected": False},
            {"positive": True, "detected": True},
            {"positive": False, "detected": True},
            {"positive": False, "detected": False},
        ]
    )
    assert metrics["true_positive"] + metrics["false_negative"] == metrics["positive_trials"] == 2
    assert metrics["false_positive"] + metrics["true_negative"] == metrics["negative_trials"] == 2
    assert metrics["recall"] == 0.5 and metrics["false_positive_rate"] == 0.5
