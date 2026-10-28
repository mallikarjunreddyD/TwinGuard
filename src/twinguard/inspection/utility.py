"""Bounded engineering proxy with marginal coverage and explicit costs."""

from .contracts import ViewpointUtility


def utility(candidate, covered, surface, priority, config, travel_s, budget_s):
    usable = set(candidate.predicted_usable_cells)
    new = usable - covered
    total = float(surface.area[surface.assets == candidate.asset_id].sum())
    fraction = surface.area_of(new) / max(total, 1e-12)
    overlap = 1 - len(new) / max(1, len(usable))
    terms = {
        "coverage": fraction,
        "deficiency": fraction * priority.terms["deficiency"],
        "risk": fraction * priority.score,
        "suitability": fraction * candidate.expected_quality,
        "cost": min(1, (travel_s + candidate.acquisition_s) / budget_s),
        "redundancy": overlap,
    }
    score = sum(
        config.utility_weights[k] * v * (-1 if k in ("cost", "redundancy") else 1)
        for k, v in terms.items()
    )
    return ViewpointUtility(score=score, terms=terms, new_cells=sorted(new))
