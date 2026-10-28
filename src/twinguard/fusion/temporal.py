from .models import TemporalDecision


def validate(evidence, rule, at, policy, actions=()):
    age = (at - evidence.acquired_at).total_seconds()
    status = "current"
    reason = "Available, recent qualified observation"
    if evidence.acquired_at > at:
        status = "future"
        reason = "Future acquisition cannot support this assessment"
    elif evidence.available_at > at:
        status = "not_available"
        reason = "Result not yet available at assessment"
    elif (
        evidence.clock_quality != "synchronized"
        or evidence.clock_uncertainty_s > policy.max_clock_uncertainty_s
    ):
        status = "clock_unknown"
        reason = "Clock quality does not establish temporal coincidence"
    elif any(
        a.asset_id == evidence.asset_id
        and a.kind == "repair"
        and evidence.modality == "geometric"
        and evidence.acquired_at <= a.at <= at
        for a in actions
    ):
        status = "historical_repaired"
        reason = "Pre-repair geometry is historical context only"
    elif age + evidence.clock_uncertainty_s > rule.max_age_s:
        status = "stale"
        reason = "Acquisition exceeds hazard-specific recency window"
    elif evidence.finding in ["invalid", "unavailable"]:
        status = "invalid"
        reason = "Invalid or unavailable measurement"
    elif (
        evidence.finding == "inconclusive"
        or evidence.quality != "good"
        or not evidence.calibration_valid
    ):
        status = "inconclusive"
        reason = "Measurement/calibration qualification insufficient"
    return TemporalDecision(
        evidence_id=evidence.evidence_id,
        hazard_id=rule.hazard_id,
        age_s=age,
        status=status,
        applicable=status == "current",
        historical_context=evidence.available_at <= at,
        reason=reason,
    )


def coincident(a, b, rule):
    if a.clock_quality != "synchronized" or b.clock_quality != "synchronized":
        return False, "Unknown clock quality"
    difference = (
        abs((a.acquired_at - b.acquired_at).total_seconds())
        + a.clock_uncertainty_s
        + b.clock_uncertainty_s
    )
    return difference <= rule.coincidence_s, "Acquisition separation including clock bounds " + str(
        difference
    ) + " s"
