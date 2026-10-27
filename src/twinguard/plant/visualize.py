"""Headless scientific visualization of actual physical state, never detection results."""

from pathlib import Path
import numpy as np


def render(snapshot, output: Path, baseline=None):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
        from matplotlib import colormaps
        from matplotlib.patches import Patch
        from matplotlib.ticker import MaxNLocator
    except ImportError as error:
        raise ValueError("Visualization requires pip install -e '.[viz]'") from error
    fig = plt.figure(figsize=(14, 10), layout="constrained")
    ax = fig.add_subplot(221, projection="3d")
    palette = colormaps["tab10"]
    for index, (aid, a) in enumerate(snapshot.assets.items()):
        # Render complete geometry; scale remains metres.
        collection = Poly3DCollection(
            a.vertices_world_m[a.faces], facecolor=palette(index), linewidths=0, alpha=0.95
        )
        ax.add_collection3d(collection)
        center = np.mean(a.vertices_world_m, axis=0)
        ax.text(*center, aid, fontsize=8)
    ax.legend(
        handles=[Patch(color=palette(i), label=aid) for i, aid in enumerate(snapshot.assets)],
        loc="upper left",
        fontsize=7,
        ncol=2,
    )
    ax.yaxis.set_major_locator(MaxNLocator(3))
    vertices = np.concatenate([a.vertices_world_m for a in snapshot.assets.values()])
    lo, hi = vertices.min(0), vertices.max(0)
    ax.set(
        xlim=(lo[0] - 0.2, hi[0] + 0.2),
        ylim=(lo[1] - 0.4, hi[1] + 0.4),
        zlim=(0, hi[2] + 0.2),
        xlabel="X (m)",
        ylabel="Y (m)",
        zlabel="Z (m)",
        title="Common physical world / asset identifiers",
    )
    ax.set_box_aspect(np.maximum(hi - lo, 0.5))
    ax.view_init(22, 65)
    wall = snapshot.assets["BW-01"]
    bx = fig.add_subplot(222)
    mid = (wall.vertices_local_m[:, 2].min() + wall.vertices_local_m[:, 2].max()) / 2
    front = np.isclose(wall.vertices_local_m[:, 2], mid, atol=0.0001)
    if baseline is not None:
        original = baseline.mesh("BW-01").vertices
        front &= np.isclose(original[:, 1], 0, atol=1e-8)
        order = np.argsort(original[front, 0])
        bx.plot(
            original[front, 0][order], original[front, 1][order] * 1000, label="Accepted baseline"
        )
    else:
        order = np.argsort(wall.vertices_local_m[front, 0])
    bx.plot(
        wall.vertices_local_m[front, 0][order],
        wall.vertices_local_m[front, 1][order] * 1000,
        label="Current physical mesh",
    )
    bx.set(
        xlabel="Wall local X (m)",
        ylabel="Outward local Y (mm)",
        title="Water-wall mid-height section (unmagnified values)",
    )
    bx.legend()
    bx.grid(alpha=0.25)
    cx = fig.add_subplot(223, projection="3d")
    support = snapshot.assets["SUP-01"]
    for points, color, label in [(support.vertices_world_m, "tab:red", "Current support")]:
        cx.add_collection3d(
            Poly3DCollection(points[support.faces], facecolor=color, alpha=0.5, label=label)
        )
    if baseline is not None:
        original = baseline.mesh("SUP-01")
        original.apply_transform(baseline.world_pose("SUP-01").matrix)
        cx.add_collection3d(
            Poly3DCollection(original.vertices[original.faces], facecolor="tab:blue", alpha=0.25)
        )
    bounds = support.vertices_world_m
    cx.set(
        xlim=(bounds[:, 0].min() - 0.3, bounds[:, 0].max() + 0.3),
        ylim=(bounds[:, 1].min() - 0.3, bounds[:, 1].max() + 0.3),
        zlim=(0, bounds[:, 2].max() + 0.3),
        xlabel="X (m)",
        ylabel="Y (m)",
        zlabel="Z (m)",
        title="Support: baseline blue / current red",
    )
    dx = fig.add_subplot(224)
    local = baseline.mesh("BW-01").vertices if baseline else wall.vertices_local_m
    mask = np.isclose(local[:, 1], 0, atol=1e-8)
    plot = dx.scatter(
        wall.vertices_local_m[mask, 0],
        wall.vertices_local_m[mask, 2],
        c=wall.surface_temperature_c[mask],
        cmap="inferno",
        s=5,
    )
    fig.colorbar(plot, ax=dx, label="Surface temperature (degC)")
    dx.set(
        xlabel="Wall local X (m)",
        ylabel="Wall local Z (m)",
        title="Underlying vertex temperature field (no camera model)",
    )
    dx.set_aspect("equal")
    fig.suptitle(
        f"SIMULATION GROUND TRUTH — t={snapshot.time_s:g} s\nPhysical surrogate; no anomaly-detection algorithm",
        fontsize=14,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=130)
    plt.close(fig)
    return output
