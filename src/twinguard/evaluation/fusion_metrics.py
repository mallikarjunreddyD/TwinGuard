"""Restricted E3 metrics, evaluated only after public predictions are sealed."""

import json
from collections import Counter
import numpy as np
from .analytics import verify_seal, wilson


def evaluate_case(predictions, label):
    verify_seal(predictions)
    history = json.loads((predictions / "history.json").read_text())
    selected = [d for d in history if d["assessment"]["asset_id"] == label["target_asset"]]
    input_file = predictions / "evidence.json"
    source_evidence = {e["evidence_id"]: e for e in json.loads(input_file.read_text())}

    def matches(d):
        supported = [source_evidence[i] for i in d["positive_ids"] if i in source_evidence]
        if label.get("localized_evidence_ids") is not None:
            return bool(set(d["positive_ids"]) & set(label["localized_evidence_ids"]))
        return any(e["hypothesis"] in label.get("expected_hypotheses", []) for e in supported)

    from datetime import datetime

    onset = datetime.fromisoformat(label["onset"])
    end = datetime.fromisoformat(label["end"])
    within = [
        d
        for d in selected
        if onset <= datetime.fromisoformat(d["assessment"]["assessed_at"]) <= end
    ]
    positive = label["event_positive"]
    critical = label.get("critical_event", False)
    advisory = any(d["assessment"]["severity"] in ["amber", "red"] for d in within)
    event_matched = any(
        d["assessment"]["severity"] in ["amber", "red"] and matches(d) for d in within
    )
    red_matched = any(d["assessment"]["severity"] == "red" and matches(d) for d in within)
    detected = event_matched if not critical else red_matched
    active = [
        d
        for d in within
        if d["assessment"]["severity"] in (["red"] if critical else ["amber", "red"]) and matches(d)
    ]
    delay = (
        (datetime.fromisoformat(active[0]["assessment"]["assessed_at"]) - onset).total_seconds()
        if positive and active
        else None
    )
    used_stale = 0
    for d in selected:
        eligible_hazards = set(d["triggered_hazards"]) if d["method"] == "F1" else None
        invalid_support = False
        for identifier in d["positive_ids"]:
            valid = [
                t
                for t in d["temporal"]
                if t["evidence_id"] == identifier
                and t["applicable"]
                and (eligible_hazards is None or t["hazard_id"] in eligible_hazards)
            ]
            if not valid:
                invalid_support = True
        used_stale += invalid_support
    notices = json.loads((predictions / "advisories.json").read_text())
    events = json.loads((predictions / "events.json").read_text())
    real_notices = [n for n in notices if n["transition"].startswith("opened")]
    incorrect_spatial = sum(
        "coincident-structural-thermal" in d["triggered_hazards"]
        and d["assessment"]["severity"] == "red"
        and any(
            c["dimension"] == "spatial" and c["status"] in ["unknown", "incompatible"]
            for c in d["compatibility"]
        )
        for d in selected
    )
    # Unknown is not a true healthy classification, even when no advisory is raised.
    result = {
        "temporal_status_counts": dict(
            Counter(t["status"] for d in selected for t in d["temporal"])
        ),
        "spatial_status_counts": dict(
            Counter(
                c["status"]
                for d in selected
                for c in d["compatibility"]
                if c["dimension"] == "spatial"
            )
        ),
        "missing_requirement_assessments": sum(bool(d["missing_requirements"]) for d in selected),
        "inconclusive_source_records": sum(
            e["finding"] in ["inconclusive", "unavailable", "invalid"]
            for e in source_evidence.values()
        ),
        "notice_transitions": dict(Counter(n["transition"] for n in notices)),
        "positive": positive,
        "detected": detected,
        "any_advisory": advisory,
        "red": red_matched,
        "event_matched": event_matched,
        "unmatched_advisory": advisory and not event_matched,
        "critical": critical,
        "delay_s": delay,
        "final_severity": selected[-1]["assessment"]["severity"],
        "unknown_fraction": sum(d["assessment"]["severity"] == "unknown" for d in within)
        / max(len(within), 1),
        "unsupported_green": sum(
            d["assessment"]["severity"] == "green" and bool(d["missing_requirements"])
            for d in within
        ),
        "stale_or_unqualified_used_assessments": used_stale,
        "duplicate_suppressions": sum(
            c["status"] == "duplicate" for d in selected for c in d["compatibility"]
        ),
        "dependence_rejections": sum(
            c["status"] == "dependent" for d in selected for c in d["compatibility"]
        ),
        "incorrect_spatial_corroborations": incorrect_spatial,
        "advisory_notices": len(real_notices),
        "event_count": len(
            [e for e in events if e["hazard_id"] != "insufficient-current-evidence"]
        ),
        "policy_trace_complete": all(
            d["policy_sha256"]
            and d["rationale"]
            and (
                d["positive_ids"]
                or d.get("historical_positive_ids")
                or d["assessment"]["severity"] not in ["amber", "red"]
            )
            for d in selected
        ),
        "explanation_missing_identified": all(
            not d["missing_requirements"] or d["assessment"]["missing_or_invalid_evidence_ids"]
            for d in selected
        ),
    }
    if "expected_severity" in label:
        result["decision_correct"] = result["final_severity"] == label["expected_severity"]
    return result


def summarize(rows):
    result = {}
    for method in ["F0", "F1"]:
        data = [r for r in rows if r["method"] == method]
        positive = [r for r in data if r["positive"]]
        negative = [r for r in data if not r["positive"]]
        tp = sum(r["detected"] for r in positive)
        fp = sum(r["any_advisory"] for r in negative) + sum(
            r.get("unmatched_advisory", False) for r in positive
        )
        fn = len(positive) - tp
        critical = [r for r in positive if r["critical"]]
        delays = [r["delay_s"] for r in positive if r["delay_s"] is not None]
        result[method] = {
            "trials": len(data),
            "positive_events": len(positive),
            "negative_scenarios": len(negative),
            "true_positive_events": tp,
            "false_advisories": fp,
            "missed_events": fn,
            "event_precision": tp / (tp + fp) if tp + fp else None,
            "event_recall": tp / len(positive) if positive else None,
            "false_advisory_rate": sum(r["any_advisory"] for r in negative) / len(negative)
            if negative
            else None,
            "wrong_condition_advisories": sum(r.get("unmatched_advisory", False) for r in positive),
            "missed_event_rate": fn / len(positive) if positive else None,
            "critical_events": len(critical),
            "critical_escalations": sum(r["red"] for r in critical),
            "mean_escalation_delay_s": float(np.mean(delays)) if delays else None,
            "recall_wilson_95": wilson(tp, len(positive)),
            "false_advisory_wilson_95": wilson(fp, len(negative)),
            "unknown_fraction_mean": float(np.mean([r["unknown_fraction"] for r in data]))
            if data
            else None,
            "unsupported_green": sum(r["unsupported_green"] for r in data),
            "stale_or_unqualified_used_assessments": sum(
                r["stale_or_unqualified_used_assessments"] for r in data
            ),
            "incorrect_spatial_corroborations": sum(
                r["incorrect_spatial_corroborations"] for r in data
            ),
            "duplicate_suppressions": sum(r["duplicate_suppressions"] for r in data),
            "decision_correct": sum(r.get("decision_correct", False) for r in data)
            if any("decision_correct" in r for r in data)
            else None,
            "trace_complete_fraction": float(np.mean([r["policy_trace_complete"] for r in data]))
            if data
            else None,
            "by_condition": {
                condition: {
                    "cases": len([r for r in data if r["condition"] == condition]),
                    "detected": sum(r["detected"] for r in data if r["condition"] == condition),
                    "positive": sum(r["positive"] for r in data if r["condition"] == condition),
                    "unknown_final": sum(
                        r["final_severity"] == "unknown"
                        for r in data
                        if r["condition"] == condition
                    ),
                }
                for condition in sorted({r["condition"] for r in data})
            },
        }
    return result
