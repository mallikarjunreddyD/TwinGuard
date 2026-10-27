"""Fixed, independently accepted synthetic as-built reference; never current truth."""

from pathlib import Path
import numpy as np
from pydantic import Field
from twinguard.core.contracts import Contract, ID, Number


class ReferenceAsset(Contract):
    asset_id: ID
    bounds_world_m: tuple[tuple[Number, Number, Number], tuple[Number, Number, Number]]
    stable: bool = False
    plane_point_world_m: tuple[Number, Number, Number] | None = None
    normal_world: tuple[Number, Number, Number] | None = None


class AcceptedReference(Contract):
    reference_id: ID
    provenance: str
    assets: list[ReferenceAsset] = Field(min_length=1)


def load_reference(path: Path):
    return AcceptedReference.model_validate_json(path.read_text())


def mask_asset(points, asset, margin=0):
    lo, hi = np.asarray(asset.bounds_world_m)
    return np.all((points >= lo - margin) & (points <= hi + margin), axis=1)


def associate(center, reference, margin=0.04):
    candidates = [
        a.asset_id for a in reference.assets if mask_asset(np.asarray([center]), a, margin)[0]
    ]
    return candidates[0] if len(candidates) == 1 else None
