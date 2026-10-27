"""Typed instrument/acquisition parameters; controller configs are not measurements."""

from typing import Annotated, Literal
from pydantic import Field, model_validator
from twinguard.core.contracts import (
    Contract,
    SensorConfiguration,
    ID,
    Number,
    Nonnegative,
    Probability,
)
from twinguard.core.spatial import Transform

Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]
Vector = tuple[Number, Number, Number]


class MeasurementNoise(Contract):
    sigma: Nonnegative = 0
    range_slope: Nonnegative = 0
    bias: Number = 0
    angular_sigma_rad: Nonnegative = 0
    quantum: Nonnegative = 0
    dropout: Probability = 0
    incidence_dropout: Probability = 0
    outlier_probability: Probability = 0
    outlier_scale: Nonnegative = 0


class PoseError(Contract):
    translation_sigma_m: Nonnegative = 0
    rotation_sigma_rad: Nonnegative = 0
    translation_bias_m: Vector = (0, 0, 0)
    rotation_bias_rad: Vector = (0, 0, 0)


class Imager(SensorConfiguration):
    backend: Literal["open3d", "numpy_bvh"] = "open3d"
    pose: Transform
    min_range_m: Nonnegative = 0.1
    max_range_m: Positive = 20
    noise: MeasurementNoise = Field(default_factory=MeasurementNoise)
    pose_error: PoseError = Field(default_factory=PoseError)
    reception_delay_s: Nonnegative = 0.1

    @model_validator(mode="after")
    def range_order(self):
        if self.max_range_m <= self.min_range_m:
            raise ValueError("Invalid instrument range")
        return self


class LidarConfig(Imager):
    modality: Literal["lidar"] = "lidar"
    channels: Annotated[int, Field(ge=1, le=128)] = 16
    horizontal_samples: Annotated[int, Field(ge=1, le=8192)] = 720
    vertical_min_rad: Number = -0.4
    vertical_max_rad: Number = 0.4
    horizontal_fov_rad: Positive = 1.4
    sweep_center_rad: Number = 0

    @model_validator(mode="after")
    def angles(self):
        import math

        if (
            self.vertical_min_rad > self.vertical_max_rad
            or max(abs(self.vertical_min_rad), abs(self.vertical_max_rad)) >= math.pi / 2
            or self.horizontal_fov_rad > 2 * math.pi
        ):
            raise ValueError("Invalid LiDAR angular limits")
        return self


class ThermalConfig(Imager):
    modality: Literal["thermal"] = "thermal"
    width: Annotated[int, Field(ge=1, le=1024)] = 128
    height: Annotated[int, Field(ge=1, le=768)] = 96
    horizontal_fov_rad: Annotated[float, Field(gt=0, lt=3.14, allow_inf_nan=False)] = 1.1
    vertical_fov_rad: Annotated[float, Field(gt=0, lt=3.14, allow_inf_nan=False)] = 0.85
    emissivity: Probability = 0.95
    reflected_temperature_c: Annotated[float, Field(ge=-273.15, allow_inf_nan=False)] = 25
    measurement_min_c: Annotated[float, Field(ge=-273.15, allow_inf_nan=False)] = -40
    measurement_max_c: Number = 500

    @model_validator(mode="after")
    def temperature_range(self):
        if self.measurement_max_c <= self.measurement_min_c:
            raise ValueError("Invalid thermal measurement limits")
        return self


class Delivery(Contract):
    dropout: Probability = 0
    duplicate_probability: Probability = 0
    delay_s: Nonnegative = 0.05
    delay_jitter_s: Nonnegative = 0
    timestamp_jitter_s: Nonnegative = 0
    interruption_windows_s: list[tuple[Nonnegative, Nonnegative]] = Field(default_factory=list)

    @model_validator(mode="after")
    def windows(self):
        if any(end < start for start, end in self.interruption_windows_s):
            raise ValueError("Invalid interruption interval")
        return self


class IoTConfig(SensorConfiguration):
    modality: Literal["iot"] = "iot"
    source: Literal["process_temperature", "surface_temperature", "pressure", "load", "vibration"]
    location_world_m: Vector | None = None
    sampling_interval_s: Positive = 1
    noise: MeasurementNoise = Field(default_factory=MeasurementNoise)
    delivery: Delivery = Field(default_factory=Delivery)
    measurement_min: Number = 0
    measurement_max: Number = 1e9
    vibration_base_rms_m_s2: Nonnegative = 0.15
    vibration_load_gain_m_s2: Nonnegative = 0.2
    vibration_variation_sigma_m_s2: Nonnegative = 0.01

    @model_validator(mode="after")
    def limits(self):
        if self.measurement_max <= self.measurement_min:
            raise ValueError("Invalid measurement limits")
        if self.source == "surface_temperature" and self.location_world_m is None:
            raise ValueError("Surface thermometer requires world location")
        if self.source == "load" and (self.measurement_min < 0 or self.measurement_max > 1):
            raise ValueError("Load limits must be normalized")
        if (
            self.source in ("surface_temperature", "process_temperature")
            and self.measurement_min < -273.15
        ):
            raise ValueError("Temperature below absolute zero")
        return self


class AcquisitionConfig(Contract):
    installation_id: ID
    configuration_version: ID = "v1"
    fidelity: Literal["L0", "L1", "L2"] = "L1"
    lidar: LidarConfig
    thermal: ThermalConfig
    iot: list[IoTConfig] = Field(min_length=1)
    event_poses: dict[str, Transform] = Field(default_factory=dict)

    @model_validator(mode="after")
    def identities(self):
        ids = [self.lidar.sensor_id, self.thermal.sensor_id] + [s.sensor_id for s in self.iot]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate sensor identifiers")
        return self
