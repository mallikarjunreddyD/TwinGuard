"""Privileged capture envelope; only the record and allowlisted arrays may be exported."""

from dataclasses import dataclass
from typing import Protocol, Any
import numpy as np
from twinguard.core.contracts import InspectionCapture
from twinguard.core.spatial import Transform
from .read import PhysicalReadView


@dataclass(frozen=True)
class CaptureProduct:
    observation: InspectionCapture
    arrays: dict[str, np.ndarray]
    evaluation_private: dict[str, Any]


class ImagingSensor(Protocol):
    def capture(
        self,
        physical: PhysicalReadView,
        event_id: str,
        provenance_id: str,
        rng,
        pose_rng,
        pose: Transform | None = None,
    ) -> CaptureProduct: ...
