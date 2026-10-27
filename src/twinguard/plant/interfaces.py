"""Private controller boundary; Phase 1 supplies the simulator implementation."""

from collections.abc import Iterable
from typing import Protocol
from twinguard.core.contracts import ScenarioDefinition
from twinguard.core.interfaces import Observation
from twinguard.evaluation.contracts import FaultInjection


class SimulationController(Protocol):
    def observations(
        self, scenario: ScenarioDefinition, faults: list[FaultInjection]
    ) -> Iterable[Observation]: ...
