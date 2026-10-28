"""Associate registered public measurements with valid analytic patch support."""

import numpy as np


def from_analytics(
    surface, points, capture, registration, geometry, available_at, acquired_at=None
):
    bounds = []
    for p in geometry.patches:
        if p.status == "valid" and p.calibration_support >= 10 and p.asset_id == "BW-01":
            half = float(p.scale_m or 0.08) / np.sqrt(3)
            center = np.asarray(p.center_world_m)
            bounds.append([(center - half).tolist(), (center + half).tolist()])
    return surface.observed(
        "BW-01",
        points,
        acquired_at or capture.acquired_at,
        available_at,
        capture.capture_id,
        registration.status == "valid",
        geometry.status == "valid" and geometry.measurement_basis == "localized_relative",
        registration.uncertainty_score_m,
        bounds,
    )
