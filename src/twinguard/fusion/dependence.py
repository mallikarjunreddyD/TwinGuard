from .models import CompatibilityDecision


def relationship(a, b, policy):
    shared = set(a.derived_from + [a.origin_identity]) & set(b.derived_from + [b.origin_identity])
    dependent = bool(
        shared
        or policy.dependence_groups.get(a.sensor_id or a.origin_identity, a.dependence_group)
        == policy.dependence_groups.get(b.sensor_id or b.origin_identity, b.dependence_group)
        or (
            policy.shared_reference_dependence
            and set(a.shared_references) & set(b.shared_references)
        )
    )
    return CompatibilityDecision(
        evidence_ids=[a.evidence_id, b.evidence_id],
        dimension="dependence",
        status="dependent" if dependent else "independent",
        reason="Shared lineage, signal group or reference"
        if dependent
        else "Distinct declared sources; independence is categorical, not probabilistic",
    )


def select(records, policy):
    groups = {}
    chosen = []
    rejected = []
    decisions = []
    for e in records:
        groups.setdefault((e.origin_identity, e.hypothesis, e.asset_id, e.scope), []).append(e)
    for group in groups.values():

        def priority(e):
            rank = (
                len(policy.algorithm_preference) - policy.algorithm_preference.index(e.algorithm)
                if e.algorithm in policy.algorithm_preference
                else 0
            )
            return rank, e.available_at, e.algorithm_version, e.source_id

        winner = max(group, key=priority)
        for e in group:
            if (e.algorithm, e.algorithm_version, e.source_id) == (
                winner.algorithm,
                winner.algorithm_version,
                winner.source_id,
            ):
                chosen.append(e)
            else:
                rejected.append(e.evidence_id)
                decisions.append(
                    CompatibilityDecision(
                        evidence_ids=[e.evidence_id, winner.evidence_id],
                        dimension="dependence",
                        status="superseded",
                        reason="Configured algorithm/version selection for the same original signal; retained in history",
                    )
                )
    return chosen, rejected, decisions
