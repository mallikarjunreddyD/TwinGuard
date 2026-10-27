"""Privileged physical read port for Phase 2; never an analytics payload."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
import numpy as np
from twinguard.core.spatial import Frame, Transform


@dataclass(frozen=True)
class Surface:
    asset_id: str
    vertices_world_m: np.ndarray
    faces: np.ndarray
    temperature_c: np.ndarray
    world_pose: Transform | None = None


@dataclass(frozen=True)
class PhysicalReadView:
    timestamp: datetime
    pressure_pa: float
    temperature_c: float
    normalized_load: float
    surfaces: tuple[Surface, ...]
    coordinate_frame: Frame
    model_version: str
    configuration_version: str
    ambient_temperature_c: float


class PhysicalStateReader(Protocol):
    def read_at(self, time_s: float) -> PhysicalReadView: ...


@dataclass(frozen=True)
class ProcessReadView:
    timestamp: datetime
    pressure_pa: float
    temperature_c: float
    normalized_load: float
    ambient_temperature_c: float
