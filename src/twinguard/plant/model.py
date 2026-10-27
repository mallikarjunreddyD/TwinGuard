from types import MappingProxyType
import numpy as np
import trimesh
from twinguard.core.contracts import Asset, Artifact
from twinguard.core.spatial import Frame, Transform
from .config import PlantConfig
from .geometry import asset_mesh


class PlantModel:
    """Accepted baseline; all public geometry/config access returns defensive copies."""

    def __init__(self, config: PlantConfig, seed: int):
        if seed < 0:
            raise ValueError("Seed must be nonnegative")
        self._config = PlantConfig.model_validate(config.model_dump())
        self.seed = seed
        self.plant_id = config.plant_id
        self._meshes = {a.asset_id: asset_mesh(a, self._config) for a in config.assets}
        self._poses: dict[str, Transform] = {}
        self._assets: dict[str, Asset] = {}
        specs = {a.asset_id: a for a in config.assets}

        def pose(aid):
            if aid in self._poses:
                return self._poses[aid]
            spec = specs[aid]
            local = Frame(kind="asset_local", reference_id=aid)
            parent = (
                Frame(kind="asset_local", reference_id=spec.parent_asset_id)
                if spec.parent_asset_id
                else Frame(kind="world", reference_id=config.plant_id)
            )
            matrix = np.eye(4)
            matrix[:3, 3] = spec.origin_m
            relative = Transform(source=local, target=parent, matrix=matrix.tolist())
            world = (
                pose(spec.parent_asset_id).compose(relative) if spec.parent_asset_id else relative
            )
            self._poses[aid] = world
            kind = {
                "water_wall": "boiler_water_wall_panel",
                "drum": "steam_drum",
                "pipe": "steam_pipeline",
                "support": "structural_support",
                "valve": "valve",
                "reference": "fixed_reference_structure",
            }[spec.kind]
            self._assets[aid] = Asset(
                asset_id=aid,
                name=aid,
                asset_type=kind,
                parent_asset_id=spec.parent_asset_id,
                geometry=Artifact(
                    artifact_id=f"baseline-{aid}",
                    uri=f"baseline/{aid}.ply",
                    media_type="application/ply",
                ),
                coordinate_frame=local,
                pose=relative,
                material={"name": spec.material, "alpha_per_k": str(spec.alpha_per_k)},
                operating_reference_id="plant-reference",
                baseline_geometry_version=config.model_version,
                inspection_region_ids=spec.inspectable_regions,
            )
            return world

        for aid in specs:
            pose(aid)

    @property
    def config(self):
        return self._config.model_copy(deep=True)

    @property
    def asset_registry(self):
        return MappingProxyType({k: v.model_copy(deep=True) for k, v in self._assets.items()})

    def mesh(self, asset_id: str):
        return self._meshes[asset_id].copy()

    def world_pose(self, asset_id: str):
        return self._poses[asset_id].model_copy(deep=True)

    def scene(self):
        scene = trimesh.Scene()
        for aid in self._meshes:
            scene.add_geometry(
                self.mesh(aid), geom_name=aid, node_name=aid, transform=self.world_pose(aid).matrix
            )
        return scene


def create_baseline_plant(config: PlantConfig, seed: int = 0) -> PlantModel:
    return PlantModel(config, seed)
