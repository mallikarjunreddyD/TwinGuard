"""Simulator configuration, not an analytics input."""

from pathlib import Path
from typing import Annotated, Literal
import yaml
from pydantic import Field, model_validator
from twinguard.core.contracts import Contract, ID, Number, Nonnegative, Probability

Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]
Vector = tuple[Number, Number, Number]


class AssetSpec(Contract):
    asset_id: ID
    kind: Literal["water_wall", "drum", "pipe", "support", "valve", "reference"]
    origin_m: Vector
    parent_asset_id: ID | None = None
    dimensions_m: dict[str, Positive]
    alpha_per_k: Nonnegative = 12e-6
    expansion_axis: Literal[0, 1, 2] = 2
    temperature_source: Literal["process", "ambient"] = "process"
    material: str = "illustrative steel"
    inspectable_regions: list[ID] = Field(default_factory=lambda: ["surface"])


class DynamicsConfig(Contract):
    reference_load: Probability = 0.5
    reference_temperature_c: Number = 180
    reference_pressure_pa: Nonnegative = 800000
    ambient_temperature_c: Number = 25
    temperature_gain_c: Nonnegative = 100
    pressure_gain_pa: Nonnegative = 600000
    temperature_tau_s: Positive = 25
    pressure_tau_s: Positive = 15
    process_variation_c: Nonnegative = 0
    variation_period_s: Positive = 60

    @model_validator(mode="after")
    def bounds(self):
        if min(self.reference_temperature_c, self.ambient_temperature_c) < -273.15:
            raise ValueError("Temperature below absolute zero")
        if self.reference_pressure_pa - self.pressure_gain_pa * self.reference_load < 0:
            raise ValueError("Load model produces negative absolute pressure")
        if (
            self.reference_temperature_c
            - self.temperature_gain_c * self.reference_load
            - self.process_variation_c
            < -273.15
        ):
            raise ValueError("Load model can produce temperature below absolute zero")
        return self


class PlantConfig(Contract):
    plant_id: ID = "plant-01"
    model_version: ID = "v1"
    configuration_version: ID = "v1"
    asset_aliases: dict[ID, ID] = Field(default_factory=lambda: {"wall-01": "BW-01"})
    panel_segments_x: Annotated[int, Field(ge=20, le=200)] = 60
    panel_segments_z: Annotated[int, Field(ge=20, le=250)] = 80
    radial_sections: Annotated[int, Field(ge=8, le=64)] = 16
    dynamics: DynamicsConfig = Field(default_factory=DynamicsConfig)
    assets: list[AssetSpec] = Field(min_length=7)

    @model_validator(mode="after")
    def topology(self):
        ids = {a.asset_id for a in self.assets}
        if len(ids) != len(self.assets):
            raise ValueError("Duplicate plant asset identifiers")
        required = {"BW-01", "DR-01", "SP-01", "SP-02", "SUP-01", "VL-01", "REF-01"}
        if not required <= ids or not set(self.asset_aliases.values()) <= ids:
            raise ValueError("Missing required plant asset or invalid alias")
        by_id = {a.asset_id: a for a in self.assets}
        needed = {
            "water_wall": {"width", "height", "thickness", "tube_radius", "tube_spacing"},
            "drum": {"length", "radius"},
            "pipe": {"length", "drop", "radius"},
            "support": {"width", "height", "beam"},
            "valve": {"radius", "length"},
            "reference": {"width", "height", "beam"},
        }
        for asset in self.assets:
            if not needed[asset.kind] <= asset.dimensions_m.keys():
                raise ValueError(f"Missing dimensions for {asset.asset_id}")
            seen = {asset.asset_id}
            parent = asset.parent_asset_id
            while parent:
                if parent not in ids or parent in seen:
                    raise ValueError("Missing parent or cyclic hierarchy")
                seen.add(parent)
                parent = by_id[parent].parent_asset_id
        return self


def load_plant_config(path: Path) -> PlantConfig:
    return PlantConfig.model_validate(yaml.safe_load(path.read_text()))
