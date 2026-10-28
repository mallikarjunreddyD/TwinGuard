import numpy as np
from .models import CompatibilityDecision


def compatible(a, b, requirement, tolerance):
    status = "compatible"
    reason = "Compatible asset context; no exact region claim"
    if a.asset_id is not None and b.asset_id is not None and a.asset_id != b.asset_id:
        status = "incompatible"
        reason = "Different physical assets"
    elif requirement == "none":
        status = "partially_compatible"
        reason = "Inspection context only; no asset/region overlap asserted"
    elif (
        a.asset_id is None
        or b.asset_id is None
        or a.association != "associated"
        or b.association != "associated"
    ):
        status = "unknown"
        reason = "Asset association is unknown or image-only"
    elif requirement == "region":
        if not a.region_comparison_possible or not b.region_comparison_possible:
            status = "unknown"
            reason = "Physical region comparison unsupported, including image-only thermal"
        elif a.spatial_reference != b.spatial_reference:
            status = "incompatible"
            reason = "Different spatial references"
        else:
            alo, ahi = np.asarray(a.bounds_world_m)
            blo, bhi = np.asarray(b.bounds_world_m)
            gap = np.maximum(np.maximum(alo - bhi, blo - ahi), 0)
            allowed = tolerance + a.spatial_uncertainty_m + b.spatial_uncertainty_m
            if np.linalg.norm(gap) > allowed:
                status = "incompatible"
                reason = "Regions do not overlap within stated tolerance/uncertainty"
            else:
                reason = "Published physical regions overlap or are sufficiently close"
    return CompatibilityDecision(
        evidence_ids=[a.evidence_id, b.evidence_id],
        dimension="spatial",
        status=status,
        reason=reason,
    )
