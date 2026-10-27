from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import numpy as np
import pytest
from twinguard.sensing.config import IoTConfig, MeasurementNoise, Delivery
from twinguard.sensing.iot import IoTSensor, generate_iot
from twinguard.plant.io import simulator_from_scenario
from test_phase2_geometry import view, plane, NOW

ROOT = Path(__file__).resolve().parents[1]


class Reader:
    def __init__(self, state):
        self.state = state

    def read_at(self, t):
        return replace(self.state, timestamp=NOW + timedelta(seconds=float(t)))


def sensor(source="pressure", **kwargs):
    args = dict(
        sensor_id="sensor-01",
        asset_id="front",
        source_type="synthetic",
        configuration_version="v1",
        description="IoT test",
        source=source,
        sampling_interval_s=1,
        measurement_min=0,
        measurement_max=2000000,
    )
    if source == "load":
        args["measurement_max"] = 1
    if source == "surface_temperature":
        args["location_world_m"] = (5, 0, 0)
    args.update(kwargs)
    return IoTConfig(**args)


@pytest.mark.parametrize(
    "source,expected,unit",
    [
        ("pressure", 800000, "Pa"),
        ("load", 0.5, "1"),
        ("process_temperature", 180, "degC"),
        ("surface_temperature", 100, "degC"),
        ("vibration", 0.25, "m/s2"),
    ],
)
def test_correct_sources_and_units(source, expected, unit):
    c = sensor(source, vibration_variation_sigma_m_s2=0)
    product = generate_iot(Reader(view(plane())), [c], 5, 42, "fixture", "synthetic")
    assert len(product.observations) == 6
    assert all(r.value == pytest.approx(expected) and r.unit == unit for r in product.observations)
    assert all(
        "expected" not in r.model_dump_json() and "reference_temperature" not in r.model_dump_json()
        for r in product.observations
    )


def test_iot_statistics_sampling_and_order():
    physical = Reader(view(plane()))
    a = sensor(noise=MeasurementNoise(sigma=200, bias=40))
    b = sensor("load", sensor_id="load", sampling_interval_s=2, noise=MeasurementNoise(sigma=0.002))
    first = generate_iot(physical, [a, b], 1000, 42, "fixture", "synthetic")
    second = generate_iot(
        physical, [a, b], 1000, 42, "fixture", "synthetic", execution_order=["load", "sensor-01"]
    )
    assert first.observations == second.observations
    pressure = [r.value for r in first.observations if r.sensor_id == "sensor-01"]
    assert len(pressure) == 1001
    assert sum(r.sensor_id == "load" for r in first.observations) == 501
    error = np.asarray(pressure) - 800000
    assert abs(error.mean() - 40) < 20
    assert abs(error.std() - 200) < 20


def test_delivery_impairments_and_gaps():
    c = sensor(
        delivery=Delivery(
            dropout=0.2,
            duplicate_probability=0.2,
            delay_s=2,
            delay_jitter_s=2,
            timestamp_jitter_s=0.1,
            interruption_windows_s=[(40, 45)],
        )
    )
    result = generate_iot(Reader(view(plane())), [c], 100, 42, "fixture", "synthetic")
    assert len(result.evaluation_private) == 101
    assert any(r["dropped"] for r in result.evaluation_private)
    assert any(r.delivery_status == "duplicate" for r in result.observations)
    assert any(r.delivery_status == "out_of_order" for r in result.observations)
    assert all(r.received_at >= r.acquired_at for r in result.observations)
    assert [r.received_at for r in result.observations] == sorted(
        r.received_at for r in result.observations
    )
    assert all(not 40 <= (r.acquired_at - NOW).total_seconds() <= 45 for r in result.observations)
    assert len({r.sequence_number for r in result.observations}) < 101


def test_quantization_and_load_limits():
    c = sensor("load", noise=MeasurementNoise(sigma=1, quantum=0.1))
    result = generate_iot(Reader(view(plane())), [c], 20, 3, "fixture", "synthetic")
    assert all(0 <= r.value <= 1 for r in result.observations)
    assert all(np.isclose(r.value / 0.1, round(r.value / 0.1)) for r in result.observations)
    assert any(r.quality == "degraded" for r in result.observations)


def test_real_plant_surface_and_process_and_no_fault_vibration_coupling():
    s0 = simulator_from_scenario(ROOT / "scenarios/S0.yaml", ROOT)
    s3 = simulator_from_scenario(ROOT / "scenarios/S3.yaml", ROOT)
    thermometer = sensor("surface_temperature", asset_id="BW-01", location_world_m=(0, 0, 1.55))
    instrument = IoTSensor(thermometer)
    assert instrument.reference(
        s3.sensing_reader(), 60, np.random.default_rng(0)
    ) - instrument.reference(s0.sensing_reader(), 60, np.random.default_rng(0)) == pytest.approx(
        12, abs=1e-8
    )
    vibration = sensor("vibration", asset_id="SUP-01")
    a = IoTSensor(vibration).reference(s0.sensing_reader(), 60, np.random.default_rng(3))
    b = IoTSensor(vibration).reference(s3.sensing_reader(), 60, np.random.default_rng(3))
    assert a == b
