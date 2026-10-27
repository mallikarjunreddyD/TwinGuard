from pathlib import Path
from typing import Annotated
import yaml
from pydantic import Field, model_validator
from twinguard.core.contracts import Contract, ID, Nonnegative, Probability

Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class AnalyticsConfig(Contract):
    configuration_id: ID = "analytics-v1"
    voxel_m: Positive = 0.01
    min_range_m: Nonnegative = 0.1
    max_range_m: Positive = 20
    statistical_outliers: bool = False
    outlier_neighbors: int = Field(default=20, ge=3)
    outlier_std_ratio: Positive = 3
    normal_radius_m: Positive = 0.26
    min_correspondences: int = Field(default=40, ge=6)
    stable_min_points: int = Field(default=60, ge=6)
    min_fitness: Probability = 0.25
    max_inlier_rmse_m: Positive = 0.08
    min_conditioning: Positive = 1e-5
    max_translation_correction_m: Positive = 0.5
    max_rotation_correction_rad: Positive = 0.2
    max_repeatability_m: Positive = 0.04
    registration_scales_m: list[Positive] = Field(default_factory=lambda: [0.15, 0.08, 0.04])
    registration_iterations: int = Field(default=35, ge=1, le=500)
    robust_scale_m: Positive = 0.025
    roi_margin_m: Nonnegative = 0.18
    patch_radius_m: Positive = 0.18
    patch_spacing_m: Positive = 0.12
    min_patch_points: int = Field(default=8, ge=3)
    min_common_coverage: Probability = 0.25
    min_common_cells: int = Field(default=3, ge=1)
    max_roughness_m: Positive = 0.015
    max_projection_m: Positive = 0.08
    change_threshold_m: Positive = 0.005
    nearest_threshold_m: Positive = 0.025
    uncertainty_floor_m: Positive = 0.004
    uncertainty_multiplier: Positive = 1.5
    min_region_patches: int = Field(default=2, ge=1)
    min_valid_patch_fraction: Probability = 0.1
    monitored_assets: list[ID] = Field(default_factory=lambda: ["BW-01", "SUP-01"])
    operating_k: Positive = 5
    load_age_limit_s: Positive = 6
    max_delay_s: Positive = 5
    operating_min_scale_temperature: Positive = 0.4
    operating_min_scale_pressure: Positive = 500
    lag_candidates_s: list[Nonnegative] = Field(
        default_factory=lambda: [0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 45.0, 60.0]
    )
    thermal_threshold_c: Positive = 4
    thermal_min_pixels: int = Field(default=4, ge=1)
    thermal_min_training_frames: int = Field(default=4, ge=2)
    thermal_max_pose_delta_m: Positive = 0.15
    thermal_max_rotation_delta_rad: Positive = 0.08
    thermal_min_valid_fraction: Probability = 0.15

    @model_validator(mode="after")
    def bounds(self):
        if self.min_range_m >= self.max_range_m:
            raise ValueError("Invalid range bounds")
        if not self.registration_scales_m:
            raise ValueError("Registration requires scales")
        return self


def load_config(path: Path):
    return AnalyticsConfig.model_validate(yaml.safe_load(path.read_text()))
