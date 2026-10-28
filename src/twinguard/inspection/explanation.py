"""Human-readable trace from stored backend decisions."""


def explain(plan):
    return plan.explanation.model_dump(mode="json")
