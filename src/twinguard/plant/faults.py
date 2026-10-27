"""Restricted fault application. Analytics must never import this module."""

import numpy as np
from twinguard.evaluation.contracts import FaultInjection


def factor_at(fault: FaultInjection, timestamp):
    age = (timestamp - fault.start_at).total_seconds()
    if age < 0 or (fault.repair_at is not None and timestamp >= fault.repair_at):
        return 0.0
    growth = min(1.0, age / fault.growth_duration_s) if fault.evolution == "linear" else 1.0
    persistence = fault.persistence or (
        "persistent"
        if fault.category in ("localized_geometric_deformation", "structural_support_displacement")
        else "recover"
    )
    if timestamp >= fault.end_at and persistence == "recover":
        if fault.recovery_duration_s == 0:
            return 0.0
        return max(0.0, 1 - (timestamp - fault.end_at).total_seconds() / fault.recovery_duration_s)
    return growth


def spatial_weights(points, fault: FaultInjection):
    """Compact C2 elliptical field; exactly zero outside configured X/Z radii."""
    p = np.asarray(points)
    radius = ((p[:, 0] - fault.center_local_m[0]) / fault.extent_m[0]) ** 2 + (
        (p[:, 2] - fault.center_local_m[2]) / fault.extent_m[2]
    ) ** 2
    return np.maximum(0, 1 - radius) ** 3


def amplitude(fault: FaultInjection):
    if fault.category == "localized_geometric_deformation":
        return (
            fault.true_displacement_m
            if fault.true_displacement_m is not None
            else fault.severity_parameters.get("amplitude_m", 0)
        )
    if fault.category == "thermal_hotspot":
        return (
            fault.true_process_deviation
            if fault.true_process_deviation is not None
            else fault.severity_parameters.get("delta_temperature_c", 0)
        )
    return (
        fault.true_process_deviation
        if fault.true_process_deviation is not None
        else fault.severity_parameters.get("pressure_deviation_pa", 0)
    )


def displacement_vector(fault: FaultInjection):
    if fault.displacement_vector_m is not None:
        return np.asarray(fault.displacement_vector_m)
    direction = np.asarray(fault.direction)
    return (
        direction
        / np.linalg.norm(direction)
        * (fault.true_displacement_m or fault.severity_parameters.get("amplitude_m", 0))
    )
