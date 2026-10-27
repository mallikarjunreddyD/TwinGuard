"""Exact first-order response to piecewise-linear load; no timestep instability."""

import math
import numpy as np
from .config import DynamicsConfig
from twinguard.core.contracts import ScenarioDefinition


def first_order_linear(x, equilibrium_start, slope, dt, tau):
    decay = math.exp(-dt / tau)
    return equilibrium_start + slope * (dt - tau) + (x - equilibrium_start + slope * tau) * decay


def operating_reference(scenario: ScenarioDefinition, config: DynamicsConfig, t: float, seed: int):
    points = scenario.operating_profile
    offsets = [p.offset_s for p in points]
    loads = [p.normalized_load for p in points]
    temperature = config.reference_temperature_c
    pressure = config.reference_pressure_pa
    # Initial equilibrium matches the configured initial profile (including startup).
    initial = loads[0] - config.reference_load
    temperature += config.temperature_gain_c * initial
    pressure += config.pressure_gain_pa * initial
    for index, point in enumerate(points):
        begin = point.offset_s
        if begin >= t:
            break
        end = min(t, offsets[index + 1] if index + 1 < len(points) else t)
        dt = end - begin
        slope = (
            (loads[index + 1] - loads[index]) / (offsets[index + 1] - begin)
            if index + 1 < len(points)
            else 0
        )
        temperature = first_order_linear(
            temperature,
            config.reference_temperature_c
            + config.temperature_gain_c * (loads[index] - config.reference_load),
            config.temperature_gain_c * slope,
            dt,
            config.temperature_tau_s,
        )
        pressure = first_order_linear(
            pressure,
            config.reference_pressure_pa
            + config.pressure_gain_pa * (loads[index] - config.reference_load),
            config.pressure_gain_pa * slope,
            dt,
            config.pressure_tau_s,
        )
    load = float(np.interp(t, offsets, loads))
    phase = np.random.default_rng(seed).uniform(0, 2 * np.pi)
    temperature += config.process_variation_c * math.sin(
        2 * math.pi * t / config.variation_period_s + phase
    )
    mode = next(
        (p.operating_mode for p in reversed(points) if p.offset_s <= t), points[0].operating_mode
    )
    return load, temperature, pressure, mode
