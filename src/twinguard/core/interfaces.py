"""Responsibility boundaries; implementations are deferred to later phases."""

from collections.abc import Iterable
from typing import Protocol
from .contracts import SensorObservation, InspectionCapture, GeometricDetection, EvidenceRecord

Observation = SensorObservation | InspectionCapture


class SensorAdapter(Protocol):
    def observations(self) -> Iterable[Observation]: ...


class AnalyticsEngine(Protocol):
    def process(
        self, observation: Observation
    ) -> Iterable[GeometricDetection | EvidenceRecord]: ...


class ObservationStore(Protocol):
    def save(self, observation: Observation) -> None: ...


# Simulation controller inputs and evaluator labels are private and intentionally
# absent from these public analytics/application interfaces.
