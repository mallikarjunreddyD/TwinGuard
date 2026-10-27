"""Order-independent physical world evaluation. No sensor observations are synthesized."""

from dataclasses import dataclass
from datetime import datetime
from collections.abc import Mapping
from typing import Any
from datetime import timedelta
from types import MappingProxyType
import numpy as np
from twinguard.core.contracts import PlantState, ScenarioDefinition
from twinguard.core.spatial import Transform, Frame
from twinguard.evaluation.contracts import FaultInjection, GroundTruthSnapshot, FaultState
from twinguard.sensing.read import PhysicalReadView, Surface, ProcessReadView
from .model import PlantModel
from .dynamics import operating_reference
from .faults import factor_at, spatial_weights, amplitude, displacement_vector


def readonly(array):
    result = np.array(array, copy=True)
    result.setflags(write=False)
    return result


@dataclass(frozen=True)
class AssetPhysicalState:
    asset_id: str
    vertices_local_m: np.ndarray
    vertices_world_m: np.ndarray
    faces: np.ndarray
    surface_temperature_c: np.ndarray
    world_pose: Transform
    normal_expansion_m: float
    structural_translation_m: np.ndarray


@dataclass(frozen=True)
class PhysicalSnapshot:
    timestamp: datetime
    time_s: float
    operating: PlantState
    assets: Mapping[str, AssetPhysicalState]
    model_version: str
    configuration_version: str


class PlantSimulator:
    def __init__(
        self, baseline: PlantModel, scenario: ScenarioDefinition, faults: list[FaultInjection]
    ):
        self.baseline = baseline
        self.scenario = ScenarioDefinition.model_validate(scenario.model_dump())
        self._faults = [FaultInjection.model_validate(f.model_dump()) for f in faults]
        self._config = baseline.config
        self._specs = {a.asset_id: a for a in self._config.assets}
        if scenario.plant_model_reference != baseline.plant_id:
            raise ValueError("Scenario plant reference mismatch")
        for identifier in scenario.asset_ids:
            if self.resolve(identifier) not in self._specs:
                raise ValueError("Unknown scenario asset")
        seen = set()
        for fault in self._faults:
            if fault.fault_id in seen:
                raise ValueError("Duplicate fault identifier")
            seen.add(fault.fault_id)
            if self.resolve(fault.asset_id) not in self._specs:
                raise ValueError("Unknown fault asset")
            if (
                fault.start_at < scenario.simulation_start
                or fault.end_at > scenario.simulation_start + timedelta(seconds=scenario.duration_s)
            ):
                raise ValueError("Fault outside scenario interval")
            if (
                fault.category == "localized_geometric_deformation"
                and self._specs[self.resolve(fault.asset_id)].kind != "water_wall"
            ):
                raise ValueError("Bulge requires water-wall asset")
            if fault.category == "abnormal_process_measurement":
                if fault.process_variable == "pressure_pa" and fault.deviation_unit not in (
                    None,
                    "Pa",
                ):
                    raise ValueError("Pressure fault requires Pa")
                if fault.process_variable == "temperature_c" and fault.deviation_unit not in (
                    None,
                    "degC",
                ):
                    raise ValueError("Temperature fault requires degC")
        allowed = {self.resolve(aid) for aid in self.scenario.asset_ids}
        for fault in self._faults:
            if self.resolve(fault.asset_id) not in allowed:
                raise ValueError("Fault asset is outside scenario asset registry")
            if (
                fault.category == "structural_support_displacement"
                and self._specs[self.resolve(fault.asset_id)].kind != "support"
            ):
                raise ValueError("Support displacement requires support asset")
            magnitude_key = {
                "localized_geometric_deformation": "amplitude_m",
                "thermal_hotspot": "delta_temperature_c",
                "abnormal_process_measurement": "pressure_deviation_pa",
                "structural_support_displacement": "amplitude_m",
            }[fault.category]
            exact = (
                fault.true_displacement_m
                if fault.category
                in ("localized_geometric_deformation", "structural_support_displacement")
                else fault.true_process_deviation
            )
            if (
                exact is None
                and magnitude_key not in fault.severity_parameters
                and fault.target_value is None
                and fault.displacement_vector_m is None
            ):
                raise ValueError("Fault requires an explicit physical magnitude")
            if (
                exact is not None
                and magnitude_key in fault.severity_parameters
                and not np.isclose(
                    exact, fault.severity_parameters[magnitude_key], atol=1e-12, rtol=0
                )
            ):
                raise ValueError("Conflicting fault magnitude and ground-truth parameters")
            if fault.category in (
                "localized_geometric_deformation",
                "thermal_hotspot",
            ) and not np.any(
                spatial_weights(self.baseline.mesh(self.resolve(fault.asset_id)).vertices, fault)
                > 0
            ):
                raise ValueError("Fault region does not intersect sampled asset surface")
        # Absolute targets cannot be combined with another disturbance on the same process variable.
        process = [f for f in self._faults if f.category == "abnormal_process_measurement"]
        for f in process:
            if (
                f.target_value is not None
                and sum(g.process_variable == f.process_variable for g in process) > 1
            ):
                raise ValueError("Incompatible simultaneous absolute process targets")

    def resolve(self, asset_id):
        return self._config.asset_aliases.get(asset_id, asset_id)

    def time_grid(self):
        step = self.scenario.time_step_s
        duration = self.scenario.duration_s
        values = np.arange(int(np.floor(duration / step)) + 1) * step
        if values[-1] < duration:
            values = np.append(values, duration)
        return values

    def _process_at(self, time_s):
        lower = min([0.0] + [i.offset_s for i in self.scenario.inspections])
        if not np.isfinite(time_s) or time_s < lower or time_s > self.scenario.duration_s:
            raise ValueError(f"Time must be within [{lower}, {self.scenario.duration_s}] seconds")
        timestamp = self.scenario.simulation_start + timedelta(seconds=float(time_s))
        load, temp, pressure, mode = operating_reference(
            self.scenario, self._config.dynamics, max(0, time_s), self.scenario.random_seed
        )
        true_temp, true_pressure = temp, pressure
        for fault in sorted(self._faults, key=lambda f: f.fault_id):
            factor = factor_at(fault, timestamp)
            if fault.category == "abnormal_process_measurement":
                reference = temp if fault.process_variable == "temperature_c" else pressure
                change = (
                    (fault.target_value - reference)
                    if fault.target_value is not None
                    else amplitude(fault)
                )
                if fault.process_variable == "temperature_c":
                    true_temp += factor * change
                else:
                    true_pressure += factor * change
                if factor:
                    mode = "abnormal_operation"
        if true_pressure < 0 or true_temp < -273.15:
            raise ValueError("Fault produces invalid physical process state")
        return timestamp, load, temp, pressure, mode, true_temp, true_pressure

    def operating_at(self, time_s: float) -> PlantState:
        timestamp, load, temp, pressure, mode, true_temp, true_pressure = self._process_at(time_s)
        return PlantState(
            state_id=f"{self.scenario.scenario_id}-t-{np.format_float_positional(float(time_s), unique=True, trim='-')}".replace(
                "-t--", "-t-minus-"
            ),
            timestamp=timestamp,
            plant_id=self.baseline.plant_id,
            operating_mode=mode,
            normalized_load=load,
            process_pressure_pa=true_pressure,
            process_temperature_c=true_temp,
            ambient_temperature_c=self._config.dynamics.ambient_temperature_c,
        )

    def state_at(self, time_s: float) -> PhysicalSnapshot:
        timestamp, load, temp, pressure, mode, true_temp, true_pressure = self._process_at(time_s)
        states = {}
        world_poses: dict[str, Transform] = {}

        def current_pose(aid):
            if aid in world_poses:
                return world_poses[aid]
            asset = self.baseline.asset_registry[aid]
            relative = asset.pose.model_copy(deep=True)
            if asset.parent_asset_id:
                pose = current_pose(asset.parent_asset_id).compose(relative)
            else:
                pose = relative
            matrix = np.asarray(pose.matrix).copy()
            translation = np.zeros(3)
            for fault in self._faults:
                if (
                    self.resolve(fault.asset_id) == aid
                    and fault.category == "structural_support_displacement"
                ):
                    translation += factor_at(fault, timestamp) * displacement_vector(fault)
            matrix[:3, 3] += translation
            result = Transform(source=pose.source, target=pose.target, matrix=matrix.tolist())
            world_poses[aid] = result
            return result

        for aid, spec in self._specs.items():
            mesh = self.baseline.mesh(aid)
            original = np.asarray(mesh.vertices)
            vertices = original.copy()
            surface_temp = (
                temp
                if spec.temperature_source == "process"
                else self._config.dynamics.ambient_temperature_c
            )
            reference_temp = (
                self._config.dynamics.reference_temperature_c
                if spec.temperature_source == "process"
                else self._config.dynamics.ambient_temperature_c
            )
            scale = spec.alpha_per_k * (surface_temp - reference_temp)
            axis = spec.expansion_axis
            vertices[:, axis] += original[:, axis] * scale
            expansion = float(np.ptp(original[:, axis]) * scale)
            temperatures = np.full(len(vertices), surface_temp)
            for fault in sorted(self._faults, key=lambda f: f.fault_id):
                if self.resolve(fault.asset_id) != aid:
                    continue
                factor = factor_at(fault, timestamp)
                if fault.category == "localized_geometric_deformation":
                    direction = np.asarray(fault.direction)
                    direction = direction / np.linalg.norm(direction)
                    vertices += (
                        spatial_weights(original, fault)[:, None]
                        * factor
                        * amplitude(fault)
                        * direction
                    )
                elif fault.category == "thermal_hotspot":
                    temperatures += spatial_weights(original, fault) * factor * amplitude(fault)
            pose = current_pose(aid)
            world = np.asarray(pose.apply(vertices.tolist(), pose.source))
            translation = (
                np.asarray(pose.matrix)[:3, 3]
                - np.asarray(self.baseline.world_pose(aid).matrix)[:3, 3]
            )
            states[aid] = AssetPhysicalState(
                aid,
                readonly(vertices),
                readonly(world),
                readonly(mesh.faces),
                readonly(temperatures),
                pose,
                expansion,
                readonly(translation),
            )
        operating = self.operating_at(time_s)
        return PhysicalSnapshot(
            timestamp,
            time_s,
            operating,
            MappingProxyType(states),
            self._config.model_version,
            self._config.configuration_version,
        )

    def sensing_reader(self):
        simulator = self

        class Reader:
            def read_process_at(self, time_s: float) -> ProcessReadView:
                state = simulator.operating_at(time_s)
                return ProcessReadView(
                    state.timestamp,
                    state.process_pressure_pa,
                    state.process_temperature_c,
                    state.normalized_load,
                    state.ambient_temperature_c,
                )

            def read_at(self, time_s: float) -> PhysicalReadView:
                state = simulator.state_at(time_s)
                surfaces = tuple(
                    Surface(
                        a.asset_id,
                        readonly(a.vertices_world_m),
                        readonly(a.faces),
                        readonly(a.surface_temperature_c),
                        a.world_pose.model_copy(deep=True),
                    )
                    for a in state.assets.values()
                )
                op = state.operating
                return PhysicalReadView(
                    state.timestamp,
                    op.process_pressure_pa,
                    op.process_temperature_c,
                    op.normalized_load,
                    surfaces,
                    Frame(kind="world", reference_id=simulator.baseline.plant_id),
                    simulator._config.model_version,
                    simulator._config.configuration_version,
                    op.ambient_temperature_c,
                )

        return Reader()

    def ground_truth_at(self, time_s: float, run_id: str = "simulation-run") -> GroundTruthSnapshot:
        state = self.state_at(time_s)
        records = []
        for fault in self._faults:
            aid = self.resolve(fault.asset_id)
            factor = factor_at(fault, state.timestamp)
            record: dict[str, Any] = {
                "fault_id": fault.fault_id,
                "asset_id": aid,
                "category": fault.category,
                "factor": factor,
                "present": bool(factor),
                "configuration": fault.model_dump(mode="json"),
            }
            if fault.category == "localized_geometric_deformation":
                applied = (
                    spatial_weights(self.baseline.mesh(aid).vertices, fault)
                    * factor
                    * amplitude(fault)
                )
                record["applied_peak_displacement_m"] = float(np.max(np.abs(applied)))
            if fault.category == "structural_support_displacement":
                record["applied_translation_m"] = (factor * displacement_vector(fault)).tolist()
            if fault.category == "thermal_hotspot":
                record["applied_peak_temperature_delta_c"] = float(
                    np.max(
                        spatial_weights(self.baseline.mesh(aid).vertices, fault)
                        * factor
                        * amplitude(fault)
                    )
                )
            if fault.category == "abnormal_process_measurement":
                record["actual_process_value"] = (
                    state.operating.process_pressure_pa
                    if fault.process_variable == "pressure_pa"
                    else state.operating.process_temperature_c
                )
            records.append(record)
        return GroundTruthSnapshot(
            truth_id=f"{run_id}-{np.format_float_positional(float(time_s), unique=True, trim='-')}",
            run_id=run_id,
            scenario_id=self.scenario.scenario_id,
            timestamp=state.timestamp,
            time_s=time_s,
            fault_states=[FaultState.model_validate(record) for record in records],
        )
