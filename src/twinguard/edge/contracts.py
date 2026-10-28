"""Authenticated operational metadata is separate from scientific measurements."""

from datetime import datetime, timezone
from typing import Literal
from pydantic import Field
from twinguard.core.contracts import Contract, ID, SensorObservation


def now():
    return datetime.now(timezone.utc)


class SourceRegistration(Contract):
    source_id: ID
    transport_identity: ID
    site_id: ID = "plant-01"
    sensors: dict[str, dict[str, str]]
    active: bool = True
    clock_quality: Literal["unknown", "uncertain", "synchronized"] = "unknown"
    clock_basis: str = "unverified"
    calibration_status: Literal["unknown", "assumed_simulation", "verified"] = "unknown"
    calibration_reference: str | None = None
    expected_interval_s: float = Field(default=5, gt=0)
    configuration_reference: str = "v1"
    allow_inspections: bool = False
    capture_sensors: dict[str, list[str]] = Field(default_factory=dict)


class Envelope(Contract):
    message_id: ID
    source_id: ID
    site_id: ID = "plant-01"
    kind: Literal["observation", "inspection"] = "observation"
    sequence: int = Field(ge=0)
    sequence_epoch: ID = "legacy"
    emitted_at: datetime
    configuration_reference: str = "v1"
    provenance_id: ID
    mode: Literal["live", "simulation_replay"] = "live"
    # Original scientific acquisition is always inside observation; this is a declared replay clock.
    replay_acquired_at: datetime | None = None
    replay_source_anchor_at: datetime | None = None
    replay_rate: float = Field(default=1, gt=0, allow_inf_nan=False)
    observation: SensorObservation | None = None
    artifact_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @classmethod
    def schema_name(cls):
        return "EdgeEnvelope"
