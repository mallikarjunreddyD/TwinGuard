"""Stable area-weighted reference cells; public clouds never carry simulator hit labels."""

from pathlib import Path
import hashlib
import numpy as np
import trimesh
from scipy.spatial import cKDTree
from .contracts import SurfaceCoverageEstimate


class ReferenceSurface:
    def __init__(self, path, expected_hash, cell_m=0.08):
        path = Path(path)
        self.hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if self.hash != expected_hash:
            raise ValueError("Accepted reference hash mismatch")
        scene = trimesh.load(path, force="scene", process=False)
        meshes = []
        assets = []
        for name in sorted(scene.graph.nodes_geometry):
            transform, key = scene.graph[name]
            mesh = scene.geometry[key].copy()
            mesh.apply_transform(transform)
            aid = name.split("_")[0]
            meshes.append(mesh)
            assets.extend([aid] * len(mesh.faces))
        self.mesh = trimesh.util.concatenate(meshes)
        self.triangle_assets = np.array(assets)
        triangles = self.mesh.triangles
        # Area quadrature at triangle centroids, grouped by deterministic asset voxel.
        centers = triangles.mean(axis=1)
        areas = self.mesh.area_faces
        keys = [(a, *np.floor(p / cell_m).astype(int)) for a, p in zip(assets, centers)]
        ordered = sorted(set(keys))
        index = {k: i for i, k in enumerate(ordered)}
        self.triangle_cell = np.array([index[k] for k in keys])
        n = len(ordered)
        self.area = np.bincount(self.triangle_cell, weights=areas, minlength=n)
        self.centers = np.column_stack(
            [
                np.bincount(self.triangle_cell, weights=areas * centers[:, j], minlength=n)
                / self.area
                for j in range(3)
            ]
        )
        self.assets = np.array([k[0] for k in ordered])
        self.tree = cKDTree(self.centers)
        import open3d as o3d

        self.o3d = o3d
        self.scene = o3d.t.geometry.RaycastingScene(nthreads=1)
        self.scene.add_triangles(
            o3d.core.Tensor(self.mesh.vertices.astype(np.float32)),
            o3d.core.Tensor(self.mesh.faces.astype(np.uint32)),
        )

    def cast(self, origin, directions):
        directions = np.asarray(directions, float)
        directions = directions / np.linalg.norm(directions, axis=1)[:, None]
        rays = np.column_stack([np.broadcast_to(origin, directions.shape), directions]).astype(
            np.float32
        )
        result = self.scene.cast_rays(self.o3d.core.Tensor(rays), nthreads=1)
        distance = result["t_hit"].numpy().astype(float)
        triangles = result["primitive_ids"].numpy().astype(int)
        good = np.isfinite(distance)
        incidence = np.zeros(len(distance))
        incidence[good] = np.abs(
            np.einsum("ij,ij->i", self.mesh.face_normals[triangles[good]], directions[good])
        )
        cells = np.full(len(distance), -1)
        cells[good] = self.triangle_cell[triangles[good]]
        return distance, incidence, cells

    def area_of(self, cells):
        ids = np.asarray(sorted(set(cells)), int)
        if len(ids) and (ids.min() < 0 or ids.max() >= len(self.area)):
            raise ValueError("Invalid reference cell")
        return float(self.area[ids].sum())

    def associate(self, world_points, tolerance_m):
        points = np.asarray(world_points, float)
        if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
            raise ValueError("Finite public Nx3 required")
        distances, ids = self.tree.query(points, distance_upper_bound=tolerance_m)
        return sorted(set(ids[np.isfinite(distances)].tolist()))

    def observed(
        self,
        asset_id,
        world_points,
        at,
        available_at,
        source_id,
        registration_valid=False,
        calibration_supported=False,
        uncertainty_m=None,
        qualified_bounds=(),
        tolerance_m=0.06,
    ):
        ids = self.associate(world_points, tolerance_m)
        ids = [i for i in ids if self.assets[i] == asset_id]
        qualified = []
        if (
            registration_valid
            and calibration_supported
            and uncertainty_m is not None
            and uncertainty_m <= tolerance_m
        ):
            for i in ids:
                if any(
                    np.all(self.centers[i] >= np.asarray(b[0]))
                    and np.all(self.centers[i] <= np.asarray(b[1]))
                    for b in qualified_bounds
                ):
                    qualified.append(i)
        return SurfaceCoverageEstimate(
            asset_id=asset_id,
            reference_hash=self.hash,
            modeled_area_m2=float(self.area[self.assets == asset_id].sum()),
            observed_cells=ids,
            qualified_cells=qualified,
            weak_cells=sorted(set(ids) - set(qualified)),
            observed_area_m2=self.area_of(ids),
            qualified_area_m2=self.area_of(qualified),
            acquired_at=at,
            available_at=available_at,
            source_ids=[source_id],
            registration_uncertainty_m=uncertainty_m,
            assumptions=[
                "Nominal accepted-reference voxel area quadrature; nearest public points within tolerance, no true triangle labels",
                "Qualification only inside unchanged analytic valid patch bounds; missing registration never qualified",
            ],
        )


def qualified_history(surface, snapshot, config):
    cells = set()
    for c in snapshot.coverage:
        if c.reference_hash != surface.hash:
            raise ValueError("Coverage map reference mismatch")
        surface.area_of(c.observed_cells)
        if any(surface.assets[i] != c.asset_id for i in c.observed_cells):
            raise ValueError("Coverage cells belong to another asset")
        if c.acquired_at and (snapshot.at - c.acquired_at).total_seconds() <= config.freshness_s:
            cells.update(c.qualified_cells)
    surface.area_of(cells)
    return cells
