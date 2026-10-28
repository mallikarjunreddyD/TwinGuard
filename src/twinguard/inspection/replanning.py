"""Causal public-state replanning; never clears or modifies F1."""

from .contracts import ReinspectionRecommendation
from .observations import fingerprint


def recommend(previous, snapshot):
    if snapshot.at < previous.at:
        raise ValueError("Replanning cannot go backwards")
    if snapshot.previous_plan_id != previous.plan_id:
        raise ValueError("Previous plan lineage required")
    failures = sum(a.unsuccessful_attempts for a in snapshot.assets)
    return ReinspectionRecommendation(
        previous_plan_id=previous.plan_id,
        snapshot_hash=fingerprint(snapshot),
        outcome="manual_review_required" if failures >= 3 else "replan",
        reasons=[
            "New public evidence and failed attempts retained; no physical fault resolution inferred"
        ],
    )
