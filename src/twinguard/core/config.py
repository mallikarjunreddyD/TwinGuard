from pathlib import Path
import yaml
from .contracts import Asset, ScenarioDefinition, SensorConfiguration
from twinguard.evaluation.contracts import FaultInjection


def load_scenario(path: Path, root: Path) -> ScenarioDefinition:
    scenario = ScenarioDefinition.model_validate(yaml.safe_load(path.read_text()))
    assets = [
        Asset.model_validate(a) for a in yaml.safe_load((root / "configs/assets.yaml").read_text())
    ]
    known = {a.asset_id for a in assets}
    for asset in assets:
        if (
            asset.parent_asset_id is None
            and asset.pose.target.reference_id != scenario.plant_model_reference
        ):
            raise ValueError("Asset world frame does not match plant model")
    if not set(scenario.asset_ids) <= known:
        raise ValueError("Scenario references missing assets")
    sensors = yaml.safe_load((root / "configs/sensors.yaml").read_text())
    sensors = [SensorConfiguration.model_validate(s) for s in sensors]
    sensor_ids = {s.sensor_id for s in sensors}
    if len(known) != len(assets) or len(sensor_ids) != len(sensors):
        raise ValueError("Duplicate asset or sensor identifiers")
    if any(a.parent_asset_id is not None and a.parent_asset_id not in known for a in assets):
        raise ValueError("Asset references missing parent")
    if any(s.asset_id not in known for s in sensors):
        raise ValueError("Sensor references missing asset")
    if not set(scenario.sensor_config_ids) <= sensor_ids or any(
        i.sensor_id not in sensor_ids for i in scenario.inspections
    ):
        raise ValueError("Unknown sensor configuration")
    for reference in scenario.fault_config_references:
        fault = FaultInjection.model_validate(
            yaml.safe_load((root / "datasets/ground_truth" / f"{reference}.yaml").read_text())
        )
        if fault.asset_id not in scenario.asset_ids:
            raise ValueError("Fault references missing scenario asset")
        end = scenario.simulation_start.timestamp() + scenario.duration_s
        if fault.start_at < scenario.simulation_start or fault.end_at.timestamp() > end:
            raise ValueError("Fault lies outside scenario interval")
    return scenario
