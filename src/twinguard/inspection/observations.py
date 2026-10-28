"""Adapters accept only public assessments and declared observation coverage."""

import hashlib
import json
from pathlib import Path
import yaml
from .contracts import PlanningConfig, PlanningSnapshot, AssetPlanningState, SurfaceCoverageEstimate


def fingerprint(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def load_config(path):
    return PlanningConfig.model_validate(yaml.safe_load(Path(path).read_text()))


def snapshot(at, assets, conditions, events, coverage=(), previous=None):
    states = []
    for aid in sorted(assets):
        trace = conditions.get(aid, {})
        assessment = trace.get("assessment", trace)
        active = [
            e
            for e in events
            if e.get("asset_id") == aid and e.get("lifecycle") not in ("resolved", "candidate")
        ]
        severity = assessment.get("severity", "unknown")
        # Latched events remain relevant even after monitoring expires.
        if any(e.get("severity") == "red" for e in active):
            severity = "red"
        elif any(e.get("severity") == "amber" for e in active):
            severity = "amber"
        states.append(
            AssetPlanningState(
                asset_id=aid,
                severity=severity,
                confidence={"high": 1, "medium": 0.5, "low": 0.2}.get(
                    assessment.get("confidence_status"), 0
                ),
                missing=trace.get("missing_requirements", []),
                advisory_ids=[e["event_id"] for e in active],
                critical_process=any(e.get("severity") == "red" for e in active),
                reinspection=bool(trace.get("reinspection_candidate")),
                thermal_image_only=any("thermal" in e.get("hazard_id", "") for e in active),
            )
        )
    return states


def validate_coverage(values, at, reference_hash):
    result = [SurfaceCoverageEstimate.model_validate(v) for v in values]
    for c in result:
        if c.reference_hash != reference_hash:
            raise ValueError("Coverage reference mismatch")
        if c.acquired_at and c.acquired_at > at or c.available_at and c.available_at > at:
            raise ValueError("Future evidence")
    return result


def load_snapshot(path):
    return PlanningSnapshot.model_validate_json(Path(path).read_text())
