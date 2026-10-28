"""Normalized, versioned need scores separate from access decisions."""

from .contracts import AssetInspectionPriority


def priorities(surface, snapshot, config):
    result = []
    for state in snapshot.assets:
        history = [c for c in snapshot.coverage if c.asset_id == state.asset_id]
        last = max((c.acquired_at for c in history if c.acquired_at), default=None)
        freshness = min(1, (snapshot.at - last).total_seconds() / config.freshness_s) if last else 1
        qualified = set(
            i
            for c in history
            if c.acquired_at and (snapshot.at - c.acquired_at).total_seconds() <= config.freshness_s
            for i in c.qualified_cells
        )
        area = float(surface.area[surface.assets == state.asset_id].sum())
        coverage = surface.area_of(qualified) / area if area else 0
        deficiency = max(1 - coverage, 1 - state.confidence if state.missing else 0)
        terms = {
            "criticality": config.criticality.get(state.asset_id, 0.5),
            "severity": {"unknown": 0.5, "green": 0, "amber": 0.6, "red": 1}[state.severity],
            "deficiency": deficiency,
            "freshness": freshness,
            "reinspection": float(state.reinspection),
            "failed_attempts": min(1, state.unsuccessful_attempts / 3),
        }
        reasons = ["Engineering need score, not failure probability"]
        if state.asset_id not in config.criticality:
            reasons.append("Criticality missing: explicit neutral .5 with operator review")
        if not history:
            reasons.append(
                "Actual coverage unknown; theoretical visibility cannot establish health"
            )
        if state.thermal_image_only:
            reasons.append("Thermal finding remains image-only; no spatial fault targeting")
        access = (
            "restricted"
            if state.asset_id in config.restricted_assets
            else "review_required"
            if state.critical_process or state.severity == "red"
            else "recommended"
        )
        result.append(
            AssetInspectionPriority(
                asset_id=state.asset_id,
                score=sum(config.priority_weights[k] * v for k, v in terms.items()),
                terms=terms,
                reasons=reasons,
                access=access,
            )
        )
    return sorted(result, key=lambda p: (-p.score, p.asset_id))
