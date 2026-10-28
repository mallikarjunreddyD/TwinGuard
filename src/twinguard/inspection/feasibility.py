"""Conservative static checks; unknown space always requires route review."""

import numpy as np
from .contracts import ViewpointFeasibility


def inside(point, box, margin=0):
    return bool(
        np.all(np.asarray(point) >= np.asarray(box.lower) - margin)
        and np.all(np.asarray(point) <= np.asarray(box.upper) + margin)
    )


def segment_box(a, b, box, margin=0):
    a = np.asarray(a)
    d = np.asarray(b) - a
    lo = np.asarray(box.lower) - margin
    hi = np.asarray(box.upper) + margin
    enter, leave = 0.0, 1.0
    for j in range(3):
        if abs(d[j]) < 1e-12:
            if a[j] < lo[j] or a[j] > hi[j]:
                return False
        else:
            u, v = sorted(((lo[j] - a[j]) / d[j], (hi[j] - a[j]) / d[j]))
            enter = max(enter, u)
            leave = min(leave, v)
    return enter <= leave


def route(surface, a, b, config):
    if not inside(a, config.allowed_volume, -config.safety_margin_m) or not inside(
        b, config.allowed_volume, -config.safety_margin_m
    ):
        return False
    if any(segment_box(a, b, box, config.safety_margin_m) for box in config.no_go):
        return False
    delta = np.asarray(b) - a
    length = np.linalg.norm(delta)
    if length < 1e-9:
        return True
    # Centerline and six offset segments form a conservative sampled corridor.
    for offset in [
        np.zeros(3),
        *[s * config.safety_margin_m * np.eye(3)[j] for j in range(3) for s in (-1, 1)],
    ]:
        dist, _, _ = surface.cast(np.asarray(a) + offset, np.asarray([delta]))
        if dist[0] < length + config.safety_margin_m:
            return False
    return True


def evaluate(surface, position, asset, config, measurement_reasons):
    reasons = list(measurement_reasons)
    if not inside(position, config.allowed_volume, -config.safety_margin_m):
        reasons.append("outside_allowed_volume")
    if not config.altitude_m[0] <= position[2] <= config.altitude_m[1]:
        reasons.append("altitude_constraint")
    if any(inside(position, b, config.safety_margin_m) for b in config.no_go):
        reasons.append("no_go_volume")
    query = surface.scene.compute_distance(
        surface.o3d.core.Tensor(np.asarray([position], np.float32))
    ).numpy()[0]
    if query < config.minimum_standoff_m + config.safety_margin_m:
        reasons.append("static_standoff_violation")
    if asset in config.restricted_assets:
        reasons.append("restricted_asset_access")
    if reasons:
        return ViewpointFeasibility(status="infeasible", reasons=reasons)
    if not config.map_complete:
        return ViewpointFeasibility(
            status="requires_route_review",
            reasons=["Unknown environmental geometry; route review required"],
        )
    return ViewpointFeasibility(
        status="feasible",
        reasons=["Static laboratory map only; all recommendations require operator review"],
    )
