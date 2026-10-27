"""First-visible-surface CPU raycasting: Open3D and an independent NumPy BVH.
No hidden vertex sampling, public hit labels, or graphics context."""

from dataclasses import dataclass
from typing import Any
import numpy as np
from .read import PhysicalReadView


@dataclass(frozen=True)
class Hits:
    distance_m: np.ndarray
    triangle_id: np.ndarray
    barycentric: np.ndarray
    incidence_cosine: np.ndarray


class NumpyRayScene:
    def __init__(self, view: PhysicalReadView, leaf_size: int = 12):
        self.triangles = np.concatenate([s.vertices_world_m[s.faces] for s in view.surfaces])
        self.temperatures = np.concatenate([s.temperature_c[s.faces] for s in view.surfaces])
        self.asset_ids = np.concatenate([np.full(len(s.faces), s.asset_id) for s in view.surfaces])
        self.e1 = self.triangles[:, 1] - self.triangles[:, 0]
        self.e2 = self.triangles[:, 2] - self.triangles[:, 0]
        normal = np.cross(self.e1, self.e2)
        self.normals = normal / np.linalg.norm(normal, axis=1)[:, None]
        self.nodes: list[Any] = []
        lo = self.triangles.min(axis=1)
        hi = self.triangles.max(axis=1)
        centers = (lo + hi) / 2

        def build(ids):
            index = len(self.nodes)
            self.nodes.append(None)
            bounds = (lo[ids].min(axis=0) - 1e-10, hi[ids].max(axis=0) + 1e-10)
            if len(ids) <= leaf_size:
                self.nodes[index] = (bounds, ids, None, None)
            else:
                axis = np.argmax(np.ptp(centers[ids], axis=0))
                ordered = ids[np.argsort(centers[ids, axis], kind="stable")]
                mid = len(ids) // 2
                left, right = build(ordered[:mid]), build(ordered[mid:])
                self.nodes[index] = (bounds, None, left, right)
            return index

        if not len(self.triangles):
            raise ValueError("Ray scene requires nonempty surfaces")
        build(np.arange(len(self.triangles)))

    def cast(self, origins, directions) -> Hits:
        origins = np.asarray(origins, float)
        directions = np.asarray(directions, float)
        if directions.ndim != 2 or directions.shape[1] != 3 or not np.isfinite(directions).all():
            raise ValueError("Expected finite Nx3 ray directions")
        if origins.shape == (3,):
            origins = np.broadcast_to(origins, directions.shape)
        if origins.shape != directions.shape or not np.isfinite(origins).all():
            raise ValueError("Invalid ray origins")
        norms = np.linalg.norm(directions, axis=1)
        if np.any(norms == 0):
            raise ValueError("Zero ray direction")
        directions = directions / norms[:, None]
        n = len(directions)
        nearest = np.full(n, np.inf)
        triangle = np.full(n, -1, dtype=int)
        bary = np.zeros((n, 3))
        # Parallel slab directions use infinite bounds and an explicit outside test.
        parallel = np.abs(directions) < 1e-15
        inverse = np.divide(1, directions, out=np.zeros_like(directions), where=~parallel)
        stack = [(0, np.arange(n))]
        while stack:
            node, ids = stack.pop()
            if not len(ids):
                continue
            (lo, hi), faces, left, right = self.nodes[node]
            a = (lo - origins[ids]) * inverse[ids]
            b = (hi - origins[ids]) * inverse[ids]
            lower = np.where(parallel[ids], -np.inf, np.minimum(a, b))
            upper = np.where(parallel[ids], np.inf, np.maximum(a, b))
            outside = np.any(parallel[ids] & ((origins[ids] < lo) | (origins[ids] > hi)), axis=1)
            enter = np.maximum(lower.max(axis=1), 0)
            leave = upper.min(axis=1)
            ids = ids[(~outside) & (leave >= enter) & (enter <= nearest[ids])]
            if not len(ids):
                continue
            if faces is None:
                stack.append((right, ids))
                stack.append((left, ids))
                continue
            d = directions[ids, None, :]
            o = origins[ids, None, :]
            edge1 = self.e1[faces]
            edge2 = self.e2[faces]
            h = np.cross(d, edge2)
            det = np.einsum("rtj,tj->rt", h, edge1)
            inv = np.divide(1, det, out=np.zeros_like(det), where=np.abs(det) > 1e-14)
            diff = o - self.triangles[faces, 0]
            u = np.einsum("rtj,rtj->rt", diff, h) * inv
            q = np.cross(diff, edge1)
            v = np.einsum("rtj,rtj->rt", d, q) * inv
            distance = np.einsum("tj,rtj->rt", edge2, q) * inv
            valid = (
                (np.abs(det) > 1e-14)
                & (u >= -1e-10)
                & (v >= -1e-10)
                & (u + v <= 1 + 1e-10)
                & (distance > 1e-9)
            )
            distance = np.where(valid, distance, np.inf)
            best = np.argmin(distance, axis=1)
            t = distance[np.arange(len(ids)), best]
            update = t < nearest[ids]
            rays = ids[update]
            best = best[update]
            nearest[rays] = t[update]
            triangle[rays] = faces[best]
            bu = u[np.arange(len(ids))[update], best]
            bv = v[np.arange(len(ids))[update], best]
            bary[rays] = np.column_stack([1 - bu - bv, bu, bv])
        incidence = np.zeros(n)
        hit = triangle >= 0
        incidence[hit] = np.abs(np.einsum("ij,ij->i", self.normals[triangle[hit]], directions[hit]))
        return Hits(nearest, triangle, bary, incidence)

    def temperature(self, hits: Hits):
        values = np.full(len(hits.distance_m), np.nan)
        valid = hits.triangle_id >= 0
        values[valid] = np.einsum(
            "ij,ij->i", self.temperatures[hits.triangle_id[valid]], hits.barycentric[valid]
        )
        return values


class Open3DRayScene:
    """Preferred CPU backend. Open3D computes first-hit distances/IDs/UVs in float32."""

    def __init__(self, view: PhysicalReadView):
        try:
            import open3d as o3d
        except ImportError as error:
            raise ImportError(
                "Open3D CPU raycasting requires pip install -e '.[sensing]'; select numpy_bvh explicitly for the tested alternative"
            ) from error
        self._o3d = o3d
        self._scene = o3d.t.geometry.RaycastingScene()
        temperatures = []
        asset_ids = []
        normals = []
        self._offsets = {}
        offset = 0
        for surface in view.surfaces:
            positions = o3d.core.Tensor(np.asarray(surface.vertices_world_m, dtype=np.float32))
            indices = o3d.core.Tensor(np.asarray(surface.faces, dtype=np.uint32))
            gid = self._scene.add_triangles(positions, indices)
            self._offsets[int(gid)] = offset
            offset += len(surface.faces)
            triangles = surface.vertices_world_m[surface.faces]
            normal = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
            normals.append(normal / np.linalg.norm(normal, axis=1)[:, None])
            temperatures.append(surface.temperature_c[surface.faces])
            asset_ids.append(np.full(len(surface.faces), surface.asset_id))
        self.temperatures = np.concatenate(temperatures)
        self.asset_ids = np.concatenate(asset_ids)
        self.normals = np.concatenate(normals)

    def cast(self, origins, directions) -> Hits:
        directions = np.asarray(directions, float)
        origins = np.asarray(origins, float)
        if directions.ndim != 2 or directions.shape[1] != 3 or not np.isfinite(directions).all():
            raise ValueError("Expected finite Nx3 ray directions")
        if origins.shape == (3,):
            origins = np.broadcast_to(origins, directions.shape)
        if origins.shape != directions.shape or not np.isfinite(origins).all():
            raise ValueError("Invalid ray origins")
        norms = np.linalg.norm(directions, axis=1)
        if np.any(norms == 0):
            raise ValueError("Zero ray direction")
        directions = directions / norms[:, None]
        rays = np.column_stack([origins, directions]).astype(np.float32)
        result = self._scene.cast_rays(self._o3d.core.Tensor(rays))
        distance = result["t_hit"].numpy().astype(float)
        valid = np.isfinite(distance)
        triangle = np.full(len(distance), -1, dtype=int)
        geometry = result["geometry_ids"].numpy()
        primitive = result["primitive_ids"].numpy()
        for gid, offset in self._offsets.items():
            mask = valid & (geometry == gid)
            triangle[mask] = offset + primitive[mask].astype(int)
        uv = result["primitive_uvs"].numpy().astype(float)
        bary = np.column_stack([1 - uv.sum(axis=1), uv])
        bary[~valid] = 0
        incidence = np.zeros(len(distance))
        incidence[valid] = np.abs(
            np.einsum("ij,ij->i", self.normals[triangle[valid]], directions[valid])
        )
        return Hits(distance, triangle, bary, incidence)

    def temperature(self, hits: Hits):
        values = np.full(len(hits.distance_m), np.nan)
        valid = hits.triangle_id >= 0
        values[valid] = np.einsum(
            "ij,ij->i", self.temperatures[hits.triangle_id[valid]], hits.barycentric[valid]
        )
        return values


def RayScene(view: PhysicalReadView, backend: str = "open3d"):
    if backend == "open3d":
        return Open3DRayScene(view)
    if backend == "numpy_bvh":
        return NumpyRayScene(view)
    raise ValueError("Unknown raycasting backend")
