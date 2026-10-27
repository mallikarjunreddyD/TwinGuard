"""Column vectors: T_target_source maps source coordinates into target coordinates."""

from typing import Literal
import numpy as np
from pydantic import BaseModel, ConfigDict, model_validator


class Frame(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["world", "asset_local", "sensor_local", "registered_world"]
    reference_id: str

    @model_validator(mode="after")
    def reference(self):
        if not self.reference_id.strip():
            raise ValueError("Frame reference_id must be nonempty")
        return self


class Transform(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Frame
    target: Frame
    matrix: list[list[float]]

    @model_validator(mode="after")
    def rigid(self):
        m = np.asarray(self.matrix)
        if m.shape != (4, 4) or not np.isfinite(m).all():
            raise ValueError("Expected finite 4x4 matrix")
        r = m[:3, :3]
        if not np.allclose(m[3], [0, 0, 0, 1], atol=1e-8, rtol=0):
            raise ValueError("Invalid homogeneous bottom row")
        if not np.allclose(r.T @ r, np.eye(3), atol=1e-8, rtol=0):
            raise ValueError("Rotation must be orthogonal")
        if not np.isclose(np.linalg.det(r), 1, atol=1e-8, rtol=0):
            raise ValueError("Rotation determinant must be +1")
        return self

    def inverse(self):
        return Transform(
            source=self.target, target=self.source, matrix=np.linalg.inv(self.matrix).tolist()
        )

    def compose(self, other: "Transform"):
        if other.target != self.source:
            raise ValueError("Coordinate-frame mismatch")
        return Transform(
            source=other.source,
            target=self.target,
            matrix=(np.asarray(self.matrix) @ other.matrix).tolist(),
        )

    def apply(self, points: list[list[float]], frame: Frame):
        if frame != self.source:
            raise ValueError("Coordinate-frame mismatch")
        p = np.asarray(points, dtype=float)
        if p.ndim != 2 or p.shape[1] != 3 or not np.isfinite(p).all():
            raise ValueError("Expected finite Nx3 points")
        return (p @ np.asarray(self.matrix)[:3, :3].T + np.asarray(self.matrix)[:3, 3]).tolist()
