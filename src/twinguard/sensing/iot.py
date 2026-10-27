"""Fixed-sensor measurements and replay-ready communication impairments."""

from dataclasses import dataclass
from datetime import timedelta
import numpy as np
import trimesh
from twinguard.core.contracts import SensorObservation
from .config import IoTConfig
from .noise import perturb, stream


@dataclass(frozen=True)
class IoTProduct:
    observations: tuple[SensorObservation, ...]
    evaluation_private: tuple[dict, ...]


class IoTSensor:
    def __init__(self, config: IoTConfig):
        self.config = config.model_copy(deep=True)

    def reference(self, reader, time_s, rng):
        c = self.config
        if c.source == "surface_temperature":
            state = reader.read_at(time_s)
            surfaces = [s for s in state.surfaces if s.asset_id == c.asset_id]
            if not surfaces:
                raise ValueError(f"Unknown sensor asset {c.asset_id}")
            surface = surfaces[0]
            triangles = surface.vertices_world_m[surface.faces]
            point = np.asarray(c.location_world_m)
            closest = trimesh.triangles.closest_point(
                triangles, np.broadcast_to(point, (len(triangles), 3))
            )
            index = np.argmin(np.linalg.norm(closest - point, axis=1))
            weights = trimesh.triangles.points_to_barycentric(
                triangles[index : index + 1], closest[index : index + 1]
            )[0]
            return float(weights @ surface.temperature_c[surface.faces[index]])
        state = (
            reader.read_process_at(time_s)
            if hasattr(reader, "read_process_at")
            else reader.read_at(time_s)
        )
        if c.source == "process_temperature":
            return state.temperature_c
        if c.source == "pressure":
            return state.pressure_pa
        if c.source == "load":
            return state.normalized_load
        # Explicit load-only phenomenological RMS feature, not a structural vibration solver.
        return max(
            0,
            c.vibration_base_rms_m_s2
            + c.vibration_load_gain_m_s2 * state.normalized_load
            + rng.normal(0, c.vibration_variation_sigma_m_s2),
        )

    def capture(self, reader, time_s, sequence_number, seed, scenario_id, provenance_id):
        c = self.config
        event = f"{scenario_id}-{c.sensor_id}-seq-{sequence_number}"
        rng = stream(seed, scenario_id, c.sensor_id, event)
        reference = self.reference(
            reader, time_s, stream(seed, scenario_id, c.sensor_id, event, "physical_feature")
        )
        state = (
            reader.read_process_at(time_s)
            if hasattr(reader, "read_process_at")
            else reader.read_at(time_s)
        )
        delivery = c.delivery
        missing = rng.random() < 1 - (1 - delivery.dropout) * (1 - c.noise.dropout) or any(
            begin <= time_s <= end for begin, end in delivery.interruption_windows_s
        )
        truth = {
            "event_id": event,
            "sensor_id": c.sensor_id,
            "sequence_number": sequence_number,
            "time_s": time_s,
            "noiseless_reference": reference,
            "dropped": bool(missing),
        }
        if missing:
            return (), truth
        measured, _, _ = perturb(np.array([reference]), c.noise, rng)
        value = float(np.clip(measured[0], c.measurement_min, c.measurement_max))
        saturated = value != measured[0]
        delay = max(
            0, delivery.delay_s + rng.uniform(-delivery.delay_jitter_s, delivery.delay_jitter_s)
        )
        received = state.timestamp + timedelta(seconds=delay)
        kind, unit = {
            "process_temperature": ("temperature", "degC"),
            "surface_temperature": ("temperature", "degC"),
            "pressure": ("pressure", "Pa"),
            "load": ("operating_load", "1"),
            "vibration": ("vibration_rms", "m/s2"),
        }[c.source]
        uncertainty = float(np.sqrt(c.noise.sigma**2 + c.noise.quantum**2 / 12))
        record = SensorObservation(
            observation_id=event,
            sensor_id=c.sensor_id,
            asset_id=c.asset_id,
            acquired_at=state.timestamp,
            received_at=received,
            sequence_number=sequence_number,
            measurement_type=kind,
            measurement_source={
                "surface_temperature": "surface",
                "vibration": "phenomenological",
                "load": "operating_state",
            }.get(c.source, "process"),
            value=value,
            unit=unit,
            uncertainty=uncertainty,
            quality="degraded" if saturated else "good",
            delivery_status="late" if delay > c.sampling_interval_s else "normal",
            provenance_id=provenance_id,
            location_reference=c.asset_id + "-mount",
            configuration_version=c.configuration_version,
            source_type="synthetic",
        )
        records = [record]
        if rng.random() < delivery.duplicate_probability:
            records.append(
                record.model_copy(
                    update={
                        "received_at": received + timedelta(seconds=0.001),
                        "delivery_status": "duplicate",
                    }
                )
            )
        truth.update(measured_value=value, measurement_error=value - reference)
        return tuple(records), truth


def generate_iot(
    reader, sensors, duration_s, seed, scenario_id, provenance_id, execution_order=None
):
    specs = {s.sensor_id: s for s in sensors}
    order = execution_order or list(specs)
    if set(order) != set(specs) or len(order) != len(specs):
        raise ValueError("Sensor execution order must include each instrument exactly once")
    observations = []
    truth = []
    for sensor_id in order:
        c = specs[sensor_id]
        sensor = IoTSensor(c)
        samples = (
            np.arange(int(np.floor(duration_s / c.sampling_interval_s)) + 1) * c.sampling_interval_s
        )
        for sequence, nominal in enumerate(samples):
            event = f"{sensor_id}-seq-{sequence}"
            rng = stream(seed, scenario_id, sensor_id, event, "clock")
            t = float(
                np.clip(
                    nominal
                    + rng.uniform(-c.delivery.timestamp_jitter_s, c.delivery.timestamp_jitter_s),
                    0,
                    duration_s,
                )
            )
            records, private = sensor.capture(reader, t, sequence, seed, scenario_id, provenance_id)
            observations.extend(records)
            truth.append(private)
    observations.sort(
        key=lambda r: (
            r.received_at,
            r.sensor_id,
            r.sequence_number,
            r.delivery_status == "duplicate",
        )
    )
    last_sequence = {}
    result = []
    for record in observations:
        if record.delivery_status != "duplicate" and record.sequence_number < last_sequence.get(
            record.sensor_id, -1
        ):
            record = record.model_copy(update={"delivery_status": "out_of_order"})
        if record.delivery_status != "duplicate":
            last_sequence[record.sensor_id] = max(
                last_sequence.get(record.sensor_id, -1), record.sequence_number
            )
        result.append(SensorObservation.model_validate(record.model_dump()))
    truth.sort(key=lambda r: (r["sensor_id"], r["sequence_number"]))
    return IoTProduct(tuple(result), tuple(truth))
