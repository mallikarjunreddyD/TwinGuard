"""Deterministic advisory state; expiry/acknowledgment never establish recovery."""

import hashlib
from .models import AdvisoryEvent, AdvisoryNotice


def event_key(asset, hazard):
    return asset + "|" + hazard


def notice(state, event, at, transition):
    identifier = (
        "notice-"
        + hashlib.sha256((event.event_id + transition + at.isoformat()).encode()).hexdigest()[:20]
    )
    if not any(n.notice_id == identifier for n in state.notices):
        state.notices.append(
            AdvisoryNotice(
                notice_id=identifier,
                event_id=event.event_id,
                asset_id=event.asset_id,
                at=at,
                transition=transition,
                action=event.action,
            )
        )


def update(state, asset, rule, positive, negative, at, actions):
    key = event_key(asset, rule.hazard_id)
    event = state.events.get(key)
    for action in sorted(actions, key=lambda a: (a.at, a.action_id)):
        if (
            action.asset_id != asset
            or action.at > at
            or (action.hazard_id and action.hazard_id != rule.hazard_id)
            or event is None
        ):
            continue
        action_key = action.action_id + "-" + rule.hazard_id
        if action_key in state.applied_actions:
            continue
        if action.kind == "acknowledge" and event.lifecycle not in ["candidate", "resolved"]:
            event.lifecycle = "acknowledged"
            event.updated_at = at
            notice(state, event, at, "acknowledged")
        elif (
            action.kind == "resolve"
            and rule.manual_resolution
            or action.kind == "repair"
            and rule.clear_on_repair
        ):
            event.lifecycle = "resolved"
            event.updated_at = at
            notice(state, event, at, "resolved_by_operator")
        state.applied_actions.append(action_key)
    ordered = sorted(positive, key=lambda e: (e.acquired_at, e.evidence_id))
    if ordered:
        latest = max(e.acquired_at for e in ordered)
        if (
            event is not None
            and event.lifecycle == "resolved"
            and latest <= event.last_observation_at
        ):
            return event
        if event is None or event.lifecycle == "resolved":
            first = ordered[0]
            identifier = (
                "event-"
                + hashlib.sha256(
                    (key + first.origin_identity + at.isoformat()).encode()
                ).hexdigest()[:20]
            )
            event = AdvisoryEvent(
                event_id=identifier,
                asset_id=asset,
                hazard_id=rule.hazard_id,
                severity=rule.severity,
                lifecycle="candidate",
                opened_at=at,
                updated_at=at,
                first_positive_at=first.acquired_at,
                last_observation_at=first.acquired_at,
                action=rule.action,
            )
            state.events[key] = event
        if latest >= event.last_observation_at:
            if (
                event.lifecycle == "candidate"
                and (latest - event.last_observation_at).total_seconds() > rule.aggregation_window_s
            ):
                event.positive_ids = []
                event.positive_origins = []
                event.positive_times = []
                event.first_positive_at = ordered[-1].acquired_at
            for e in ordered:
                if e.origin_identity not in event.positive_origins:
                    event.positive_origins.append(e.origin_identity)
                    event.positive_ids.append(e.evidence_id)
                    if e.acquired_at not in event.positive_times:
                        event.positive_times.append(e.acquired_at)
            event.last_observation_at = latest
            event.recovery_ids = []
            event.recovery_times = []
            event.recovery_started_at = None
            event.recovery_last_at = None
            duration = (latest - event.first_positive_at).total_seconds()
            if event.lifecycle == "candidate" and (
                rule.immediate
                or (
                    len(event.positive_times) >= rule.min_positive_count
                    and duration >= rule.min_duration_s
                )
            ):
                event.lifecycle = "escalated" if rule.severity == "red" else "active"
                event.updated_at = at
                notice(state, event, at, "opened-" + rule.severity)
            event.monitoring_unavailable = False
    elif event and event.lifecycle != "resolved":
        normals = sorted(
            [
                e
                for e in negative
                if e.recovery_eligible and e.acquired_at > event.last_observation_at
            ],
            key=lambda e: e.acquired_at,
        )
        for e in normals:
            if e.origin_identity in event.recovery_ids:
                continue
            event.recovery_ids.append(e.origin_identity)
            if e.acquired_at not in event.recovery_times:
                event.recovery_times.append(e.acquired_at)
            if event.recovery_started_at is None:
                event.recovery_started_at = e.acquired_at
            event.recovery_last_at = e.acquired_at
        if (
            rule.automatic_recovery
            and event.recovery_started_at is not None
            and len(event.recovery_times) >= rule.recovery_count
            and (event.recovery_last_at - event.recovery_started_at).total_seconds()
            >= rule.recovery_duration_s
        ):
            event.lifecycle = "resolved"
            event.updated_at = at
            notice(state, event, at, "qualified_recovery")
        event.monitoring_unavailable = not bool(negative)
    return event


def baseline_update(state, asset, severity, support, at):
    """F0 emits label-transition records only; no F1 recovery or independence semantics."""
    key = asset + "|F0"
    event = state.events.get(key)
    if severity in ["amber", "red"]:
        if event is None or event.lifecycle == "resolved":
            source = state.evidence[support[0]]
            event = AdvisoryEvent(
                event_id="f0-event-"
                + hashlib.sha256((asset + at.isoformat()).encode()).hexdigest()[:20],
                asset_id=asset,
                hazard_id="two-signal-agreement",
                severity=severity,
                lifecycle="escalated" if severity == "red" else "active",
                opened_at=at,
                updated_at=at,
                first_positive_at=source.acquired_at,
                last_observation_at=source.acquired_at,
                positive_ids=list(support),
                action="Review the simple modality-agreement advisory; this comparator does not apply hazard-specific protection rules",
            )
            state.events[key] = event
            notice(state, event, at, "opened-" + severity)
        elif event.severity != severity:
            event.severity = severity
            event.lifecycle = "escalated" if severity == "red" else "active"
            event.updated_at = at
            notice(state, event, at, "baseline-transition-" + severity)
        return event
    if event and event.lifecycle != "resolved":
        event.lifecycle = "resolved"
        event.updated_at = at
        notice(state, event, at, "baseline-cleared-on-latest-values")
    return None
