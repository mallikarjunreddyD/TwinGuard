"""Deterministic local meshes with metre units; no CAD/network dependencies."""

import numpy as np
import trimesh
from .config import AssetSpec, PlantConfig


def cylinder_between(start, end, radius, sections, axial=1):
    start, end = np.asarray(start, float), np.asarray(end, float)
    length = np.linalg.norm(end - start)
    angles = np.arange(sections) * 2 * np.pi / sections
    vertices = [
        [radius * np.cos(a), radius * np.sin(a), z]
        for z in np.linspace(0, length, axial + 1)
        for a in angles
    ]
    faces = []
    for j in range(axial):
        for i in range(sections):
            a, b = j * sections + i, j * sections + (i + 1) % sections
            c, d = a + sections, b + sections
            faces.extend([[a, b, d], [a, d, c]])
    vertices.extend([[0, 0, 0], [0, 0, length]])
    bottom, top = len(vertices) - 2, len(vertices) - 1
    for i in range(sections):
        n = (i + 1) % sections
        faces.extend([[bottom, n, i], [top, axial * sections + i, axial * sections + n]])
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    matrix = trimesh.geometry.align_vectors([0, 0, 1], (end - start) / length)
    matrix[:3, 3] = start
    mesh.apply_transform(matrix)
    return mesh


def panel(width, height, thickness, nx, nz):
    vertices = [
        [x, y, z]
        for y in (0, -thickness)
        for z in np.linspace(0, height, nz + 1)
        for x in np.linspace(-width / 2, width / 2, nx + 1)
    ]
    n = (nx + 1) * (nz + 1)
    faces = []
    for j in range(nz):
        for i in range(nx):
            a = j * (nx + 1) + i
            b = a + 1
            c = a + nx + 1
            d = c + 1
            faces.extend([[a, c, d], [a, d, b], [a + n, b + n, d + n], [a + n, d + n, c + n]])
    perimeter = (
        list(range(nx + 1))
        + [j * (nx + 1) + nx for j in range(1, nz + 1)]
        + [nz * (nx + 1) + i for i in range(nx - 1, -1, -1)]
        + [j * (nx + 1) for j in range(nz - 1, 0, -1)]
    )
    for a, b in zip(perimeter, perimeter[1:] + perimeter[:1]):
        faces.extend([[a, b, b + n], [a, b + n, a + n]])
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)


def box(extents, center):
    mesh = trimesh.creation.box(extents=extents)
    mesh.apply_translation(center)
    return mesh


def asset_mesh(spec: AssetSpec, config: PlantConfig):
    d = spec.dimensions_m
    s = config.radial_sections
    if spec.kind == "water_wall":
        pieces = [
            panel(
                d["width"],
                d["height"],
                d["thickness"],
                config.panel_segments_x,
                config.panel_segments_z,
            )
        ]
        count = int(round(d["width"] / d["tube_spacing"])) + 1
        for x in np.linspace(-d["width"] / 2, d["width"] / 2, count):
            pieces.append(
                cylinder_between(
                    [x, -d["thickness"] - d["tube_radius"], 0],
                    [x, -d["thickness"] - d["tube_radius"], d["height"]],
                    d["tube_radius"],
                    s,
                    config.panel_segments_z,
                )
            )
    elif spec.kind == "drum":
        pieces = [
            cylinder_between([-d["length"] / 2, 0, 0], [d["length"] / 2, 0, 0], d["radius"], s * 2)
        ]
    elif spec.kind == "pipe":
        sign = -1 if spec.asset_id == "SP-02" else 1
        end = [sign * d["length"], 0, 0]
        pieces = [
            cylinder_between([0, 0, 0], end, d["radius"], s),
            cylinder_between(end, [end[0], 0, -sign * d["drop"]], d["radius"], s),
        ]
        if sign == -1:
            pieces.append(
                cylinder_between([end[0], 0, d["drop"]], [0, 0, d["drop"]], d["radius"], s)
            )
            pieces.append(
                cylinder_between(
                    [0, 0, 0], [d.get("connection_length", 0.15), 0, 0], d["radius"], s
                )
            )
        else:
            pieces.append(
                cylinder_between(
                    [end[0], 0, -d["drop"]],
                    [end[0] - d.get("connection_length", 0.75), 0, -d["drop"]],
                    d["radius"],
                    s,
                )
            )
    elif spec.kind in ("support", "reference"):
        w, h, b = d["width"], d["height"], d["beam"]
        pieces = [box([b, b, h], [x, 0, h / 2]) for x in (-w / 2, w / 2)]
        pieces.append(box([w + b, b, b], [0, 0, h - b / 2]))
    else:
        pieces = [
            cylinder_between([0, 0, -d["length"] / 2], [0, 0, d["length"] / 2], d["radius"], s),
            box([0.06, 0.25, 0.06], [0, 0.15, 0]),
            cylinder_between([0, 0.25, 0], [0, 0.28, 0], d["radius"] * 1.5, s),
        ]
    mesh = trimesh.util.concatenate(pieces)
    validate_mesh(mesh)
    return mesh


def validate_mesh(mesh):
    vertices, faces = np.asarray(mesh.vertices), np.asarray(mesh.faces)
    if vertices.ndim != 2 or vertices.shape[1] != 3 or not np.isfinite(vertices).all():
        raise ValueError("Invalid mesh vertices")
    if faces.ndim != 2 or faces.shape[1] != 3 or faces.min() < 0 or faces.max() >= len(vertices):
        raise ValueError("Invalid mesh faces")
    if np.any(mesh.area_faces <= 1e-14):
        raise ValueError("Degenerate mesh triangle")
