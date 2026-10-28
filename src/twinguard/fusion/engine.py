"""Pure hazard-aware advisory assessment. No I/O, wall clock or plant control."""

import itertools
import hashlib
from twinguard import __version__
from twinguard.core.contracts import ConditionAssessment
from .models import FusionState, DecisionTrace, CompatibilityDecision, HazardRule, AdvisoryEvent
from .policies import policy_hash
from .temporal import validate, coincident
from .spatial import compatible
from .dependence import relationship, select
from .lifecycle import update, notice, baseline_update


RANK = {"unknown": 0, "green": 1, "amber": 2, "red": 3}


def _sensor_known(e, policy):
    return e.modality != "fixed_sensor" or any(
        a.sensor_id == e.sensor_id
        and a.asset_id == e.asset_id
        and a.unit == e.unit
        and a.calibration_status
        in (
            ["verified", "assumed_simulation"]
            if policy.deployment_mode == "illustrative_simulation"
            else ["verified"]
        )
        for a in policy.authorities
    )


def _critical(e, policy):
    authority = next(
        (
            a
            for a in policy.authorities
            if a.sensor_id == e.sensor_id and a.asset_id == e.asset_id and a.unit == e.unit
        ),
        None,
    )
    return bool(
        e.authoritative_limit
        and e.measurement_basis == "configured_instrument_reading"
        and authority
        and authority.critical_limit is not None
        and e.observed_value is not None
        and authority.measurement_min <= e.observed_value <= authority.measurement_max
        and e.observed_value >= authority.critical_limit
        and authority.calibration_status
        in (
            ["verified", "assumed_simulation"]
            if policy.deployment_mode == "illustrative_simulation"
            else ["verified"]
        )
    )


def assess(
    current_state,
    newly_available_evidence,
    policy,
    assessment_time,
    actions=(),
    method="F1",
    mode="online",
):
    if assessment_time.tzinfo is None or method not in ["F0", "F1"]:
        raise ValueError("Assessment requires a timezone-aware time and F0/F1 method")
    state = current_state.model_copy(deep=True)
    if state.method not in [None, method]:
        raise ValueError("Checkpoint method differs; start an explicit new replay")
    state.method = method
    digest = policy_hash(policy)
    if state.policy_sha256 not in [None, digest]:
        raise ValueError("Checkpoint policy differs; explicit new-policy replay is required")
    if state.assessed_at is not None and assessment_time < state.assessed_at:
        raise ValueError("Online state cannot be assessed backward; replay from a prior checkpoint")
    state.policy_sha256 = digest
    duplicate = []
    for e in newly_available_evidence:
        old = state.evidence.get(e.evidence_id)
        if old:
            excluded = {"received_at", "available_at", "processed_at", "availability_basis"}
            if old.model_dump(exclude=excluded) != e.model_dump(exclude=excluded):
                raise ValueError("Conflicting payload for an evidence ID")
            duplicate.append(
                CompatibilityDecision(
                    evidence_ids=[e.evidence_id],
                    dimension="dependence",
                    status="duplicate",
                    reason="Repeated delivery retained once; no independent confirmation",
                )
            )
        else:
            state.evidence[e.evidence_id] = e
    available = [e for e in state.evidence.values() if e.available_at <= assessment_time]
    selected, rejected, dependence = select(available, policy)
    # Earlier sensor samples remain in state/history but do not overwrite a newer reading.
    latest = {}
    for e in selected:
        key = (
            (e.sensor_id, e.hypothesis, e.asset_id, e.scope)
            if e.sensor_id
            else (e.modality, e.hypothesis, e.asset_id, e.scope)
        )
        latest[key] = max(latest.get(key, e.acquired_at), e.acquired_at)
    new_ids = {e.evidence_id for e in newly_available_evidence}

    def is_latest(e):
        key = (
            (e.sensor_id, e.hypothesis, e.asset_id, e.scope)
            if e.sensor_id
            else (e.modality, e.hypothesis, e.asset_id, e.scope)
        )
        return e.acquired_at == latest[key]

    trace_records = [e for e in selected if is_latest(e) or e.evidence_id in new_ids]
    decisions = []
    for asset, asset_type in sorted(policy.assets.items()):
        context = [
            e
            for e in trace_records
            if e.asset_id == asset or (asset_type == "inspection" and e.asset_id is None)
        ]
        compatibility = duplicate + dependence
        temporal = []
        rationale = []
        conflicts = []
        support = []
        current_support = []
        policy_rejected = []
        negatives = []
        triggered = []
        active = []
        for rule in policy.rules:
            if asset_type not in rule.asset_types:
                continue
            matching = [
                e
                for e in context
                if e.hypothesis in rule.hypotheses
                and e.modality in rule.modalities
                and (rule.required_scope is None or e.scope == rule.required_scope)
            ]
            candidates = []
            normal = []
            for e in matching:
                result = validate(e, rule, assessment_time, policy, actions)
                key = (
                    (e.sensor_id, e.hypothesis, e.asset_id, e.scope)
                    if e.sensor_id
                    else (e.modality, e.hypothesis, e.asset_id, e.scope)
                )
                if result.applicable and e.acquired_at < latest[key]:
                    result = result.model_copy(
                        update={
                            "status": "superseded",
                            "applicable": False,
                            "reason": "Older acquisition retained in history; newer available observation takes precedence",
                        }
                    )
                temporal.append(result)
                if result.applicable and not _sensor_known(e, policy):
                    policy_rejected.append(e.evidence_id)
                    rationale.append(
                        "Rejected "
                        + e.evidence_id
                        + ": unknown/unverified installed sensor association or calibration"
                    )
                spatial_eligible = rule.spatial_requirement == "none" or (
                    e.association == "associated" and e.asset_id is not None
                )
                if result.applicable and not spatial_eligible:
                    policy_rejected.append(e.evidence_id)
                    compatibility.append(
                        CompatibilityDecision(
                            evidence_ids=[e.evidence_id],
                            dimension="spatial",
                            status="unknown",
                            reason="Association is not qualified for this asset-specific hazard; retain inspection context only",
                        )
                    )
                if result.applicable and _sensor_known(e, policy) and spatial_eligible:
                    if e.finding == "positive" and (
                        not rule.critical_limit_only or _critical(e, policy)
                    ):
                        candidates.append(e)
                    elif e.finding == "negative":
                        normal.append(e)
            for e in state.evidence.values():
                if (
                    e.available_at > assessment_time
                    and (e.asset_id == asset or (asset_type == "inspection" and e.asset_id is None))
                    and e.hypothesis in rule.hypotheses
                ):
                    temporal.append(validate(e, rule, assessment_time, policy, actions))
            if rule.min_independent > 1:
                outside = [
                    e
                    for e in selected
                    if e.finding == "positive"
                    and is_latest(e)
                    and validate(e, rule, assessment_time, policy, actions).applicable
                    and e.asset_id != asset
                    and e.hypothesis in rule.hypotheses
                    and e.modality in rule.modalities
                ]
                for local in candidates:
                    for other in outside:
                        compatibility.append(
                            compatible(
                                local, other, rule.spatial_requirement, policy.spatial_tolerance_m
                            )
                        )
            accepted = []
            for subset in itertools.combinations(
                sorted(candidates, key=lambda e: e.evidence_id), rule.min_independent
            ):
                okay = True
                if (
                    rule.require_distinct_modalities
                    and len({e.modality for e in subset}) < rule.min_independent
                ):
                    okay = False
                for a, b in itertools.combinations(subset, 2):
                    spatial = compatible(a, b, rule.spatial_requirement, policy.spatial_tolerance_m)
                    dependency = relationship(a, b, policy)
                    temporal_ok, reason = coincident(a, b, rule)
                    compatibility.extend(
                        [
                            spatial,
                            dependency,
                            CompatibilityDecision(
                                evidence_ids=[a.evidence_id, b.evidence_id],
                                dimension="temporal",
                                status="compatible" if temporal_ok else "incompatible",
                                reason=reason,
                            ),
                        ]
                    )
                    if (
                        spatial.status not in ["compatible", "partially_compatible"]
                        or dependency.status != "independent"
                        or not temporal_ok
                    ):
                        okay = False
                if okay:
                    accepted.extend(e for e in subset if e not in accepted)
            if rule.min_independent > 1 and normal:
                # A single normal cannot disprove a multimodal hazard; no automatic clearing.
                pending = state.events.get(asset + "|" + rule.hazard_id)
                if pending is None or pending.lifecycle != "candidate":
                    normal = []
            if accepted:
                triggered.append(rule.hazard_id)
                support.extend(e.evidence_id for e in accepted)
                current_support.extend(e.evidence_id for e in accepted)
                rationale.append(rule.hazard_id + ": " + rule.rationale)
            negatives.extend(e.evidence_id for e in normal)
            if accepted and normal:
                conflicts.append(
                    rule.hazard_id
                    + ": qualified positive and negative evidence retained; positive is not vetoed"
                )
            if method == "F1":
                event = update(state, asset, rule, accepted, normal, assessment_time, actions)
                if event and event.lifecycle not in ["candidate", "resolved"]:
                    active.append(event)
                    support.extend(event.positive_ids)
                    if not accepted:
                        rationale.append(
                            rule.hazard_id
                            + ": active advisory retained pending qualified recovery ("
                            + str(rule.recovery_count)
                            + " new normal acquisitions spanning "
                            + str(rule.recovery_duration_s)
                            + " s), or authorized review; acknowledgment/expiry alone does not resolve it"
                        )
                    if event.monitoring_unavailable:
                        rationale.append(
                            rule.hazard_id
                            + ": active event retained without current recovery evidence"
                        )
        missing = []
        abnormal_required = []
        for requirement in [r for r in policy.requirements if r.asset_id == asset]:
            synthetic = HazardRule(
                hazard_id="coverage-" + requirement.requirement_id,
                hypotheses=[requirement.hypothesis],
                asset_types=[asset_type],
                modalities=["fixed_sensor", "geometric", "thermal"],
                max_age_s=requirement.max_age_s,
                action="Verify monitoring coverage",
                rationale="Explicit green coverage requirement",
            )
            eligible = [
                e
                for e in context
                if e.hypothesis == requirement.hypothesis
                and e.scope == requirement.scope
                and (requirement.sensor_id is None or e.sensor_id == requirement.sensor_id)
            ]
            valid = []
            for e in eligible:
                check = validate(e, synthetic, assessment_time, policy, actions)
                temporal.append(check)
                key = (
                    (e.sensor_id, e.hypothesis, e.asset_id, e.scope)
                    if e.sensor_id
                    else (e.modality, e.hypothesis, e.asset_id, e.scope)
                )
                if check.applicable and _sensor_known(e, policy) and e.acquired_at == latest[key]:
                    valid.append(e)
            if not valid:
                missing.append(requirement.requirement_id)
            elif any(e.finding == "positive" for e in valid):
                abnormal_required.append(requirement.requirement_id)
        monitoring = None
        if method == "F1" and policy.missing_monitoring_advisory:
            monitoring_key = asset + "|monitoring"
            monitoring = state.events.get(monitoring_key)
            if missing:
                if monitoring is None or monitoring.lifecycle == "resolved":
                    monitoring = AdvisoryEvent(
                        event_id="monitoring-"
                        + hashlib.sha256(
                            (asset + assessment_time.isoformat()).encode()
                        ).hexdigest()[:20],
                        asset_id=asset,
                        hazard_id="insufficient-current-evidence",
                        severity="amber",
                        lifecycle="active",
                        opened_at=assessment_time,
                        updated_at=assessment_time,
                        first_positive_at=assessment_time,
                        last_observation_at=assessment_time,
                        action="Verify missing/invalid monitoring; this is unavailable evidence, not a diagnosed equipment fault",
                        monitoring_unavailable=True,
                    )
                    state.events[monitoring_key] = monitoring
                    notice(state, monitoring, assessment_time, "monitoring_unavailable")
            elif monitoring and monitoring.lifecycle != "resolved":
                monitoring.lifecycle = "resolved"
                monitoring.updated_at = assessment_time
                notice(state, monitoring, assessment_time, "monitoring_restored")
        if method == "F0":
            # Fixed experimental comparator: latest available validity only; no age/region/dependence policy.
            baseline = [
                e
                for e in context
                if e.finding == "positive"
                and e.quality == "good"
                and e.calibration_valid
                and e.acquired_at
                == latest[
                    (e.sensor_id, e.hypothesis, e.asset_id, e.scope)
                    if e.sensor_id
                    else (e.modality, e.hypothesis, e.asset_id, e.scope)
                ]
            ]
            modalities = {e.modality for e in baseline}
            count = len(modalities)
            severity = (
                "red"
                if count >= 3
                else "amber"
                if count >= 2
                else "unknown"
                if baseline or missing
                else "green"
            )
            support = [e.evidence_id for e in baseline]
            baseline_event = baseline_update(state, asset, severity, support, assessment_time)
            active = [baseline_event] if baseline_event else []
            current_support = list(support)
            triggered = ["two-signal-agreement"] if count >= 2 else []
            rationale = [
                "F0 fixed two-modality amber / three-modality red; one abnormal modality is recorded for review without escalation"
            ]
        else:
            severity = (
                max([e.severity for e in active], key=lambda v: RANK[v])
                if active
                else "unknown"
                if missing or abnormal_required
                else "green"
            )
            if not any(r.asset_id == asset for r in policy.requirements) and not active:
                severity = "unknown"
                rationale.append(
                    "No normal-coverage requirements are configured for this asset scope; its condition remains unknown"
                )
        unknown = [e.evidence_id for e in context if e.finding not in ["positive", "negative"]]
        stale = [t.evidence_id for t in temporal if not t.applicable]
        if any(
            e.finding == "negative" and e.measurement_basis == "localized_relative" for e in context
        ):
            rationale.append(
                "Localized wall-relative negatives do not establish global displacement, support condition or boiler safety"
            )
        if any(e.association == "image_only" for e in context):
            rationale.append(
                "Image-only thermal finding is inspection context; no physical overlap asserted"
            )
        if any(e.finding == "positive" for e in context) and any(
            e.finding == "negative" for e in context
        ):
            conflicts.append(
                "Positive and negative scopes/modalities retained; negative evidence does not veto a different hypothesis"
            )
        if missing:
            rationale.append("Required monitoring missing/unqualified: " + ", ".join(missing))
        if abnormal_required and not active:
            rationale.append(
                "Qualified abnormal required channels await applicable activation/persistence: "
                + ", ".join(abnormal_required)
            )
        if not rationale:
            rationale = [
                "No active abnormality within required qualified evidence; green is not a safety certificate"
            ]
        confidence = (
            "limited"
            if severity in ["amber", "red"]
            and (missing or len({e.modality for e in context if e.evidence_id in support}) < 2)
            else "supported"
            if severity != "unknown"
            else "insufficient"
        )
        action = (
            "; ".join(sorted({e.action for e in active}))
            if active
            else "Verify missing monitoring and perform targeted reinspection"
            if severity == "unknown"
            else "Continue scoped monitoring; no automatic control or safety certification"
        )
        identifier = (
            "assessment-"
            + hashlib.sha256(
                (asset + assessment_time.isoformat() + digest + method).encode()
            ).hexdigest()[:20]
        )
        assessment = ConditionAssessment(
            assessment_id=identifier,
            asset_id=asset,
            assessed_at=assessment_time,
            severity=severity,
            confidence_status=confidence,
            supporting_evidence_ids=sorted(set(support)),
            missing_or_invalid_evidence_ids=sorted(set(unknown + stale + missing)),
            recommended_action=action,
            policy_id=policy.policy_id,
            policy_version=policy.version,
            human_review="pending" if severity != "green" else "not_required",
        )
        decisions.append(
            DecisionTrace(
                assessment=assessment,
                method=method,
                policy_sha256=digest,
                triggered_hazards=triggered,
                positive_ids=sorted(set(current_support)),
                historical_positive_ids=sorted(set(support) - set(current_support)),
                negative_ids=sorted(set(negatives)),
                missing_requirements=missing,
                rejected_ids=sorted(set(rejected + policy_rejected)),
                temporal=temporal,
                compatibility=compatibility,
                rationale=rationale,
                conflicts=conflicts,
                event_ids=[e.event_id for e in active]
                + (
                    [monitoring.event_id]
                    if monitoring and monitoring.lifecycle != "resolved"
                    else []
                ),
                replay_mode=mode,
                software_version=__version__,
            )
        )
    state.assessed_at = assessment_time
    return state, decisions


def replay(
    evidence, policy, at=None, actions=(), state=None, method="F1", mode="online", timeline=()
):
    state = state or FusionState()
    history = []
    times = sorted(
        {e.available_at for e in evidence}
        | {a.at for a in actions}
        | set(timeline)
        | ({at} if at else set())
    )
    for timestamp in times:
        if at is not None and timestamp > at:
            continue
        if state.assessed_at is not None and timestamp < state.assessed_at:
            continue
        incoming = sorted(
            [e for e in evidence if e.available_at == timestamp], key=lambda e: e.evidence_id
        )
        state, decisions = assess(state, incoming, policy, timestamp, actions, method, mode)
        history.extend(decisions)
    return state, history
