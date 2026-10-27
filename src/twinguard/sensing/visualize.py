"""Plots of actual measured observations; no hidden geometry or reference overlays."""

from pathlib import Path
import numpy as np
from twinguard.core.contracts import InspectionCapture
from twinguard.core.observations import load_public_observations, load_capture_arrays


def visualize_run(root: Path):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise ImportError("Sensor visualization requires pip install -e '.[viz]'") from error
    records = load_public_observations(root)
    output = root / "visualizations"
    output.mkdir(exist_ok=True)
    scans = [r for r in records if isinstance(r, InspectionCapture) and r.modality == "lidar"]
    if scans:
        fig = plt.figure(figsize=(10, 7))
        ax = fig.add_subplot(111, projection="3d")
        for record in scans:
            points = load_capture_arrays(root, record)["points_m"]
            matrix = np.asarray(record.sensor_pose.matrix)
            measured = points @ matrix[:3, :3].T + matrix[:3, 3]
            ax.scatter(*measured[:: max(1, len(measured) // 10000)].T, s=1, label=record.capture_id)
            origin = matrix[:3, 3]
            direction = matrix[:3, 0]
            ax.scatter(*origin, s=50, marker="^")
            ax.quiver(*origin, *direction, length=0.6, color="black")
        ax.set(
            xlabel="Reported world X (m)",
            ylabel="Reported world Y (m)",
            zlabel="Reported world Z (m)",
            title="Independent measured LiDAR returns / reported inspection poses",
        )
        ax.legend(fontsize=7)
        fig.tight_layout()
        fig.savefig(output / "scan_comparison.png", dpi=140)
        plt.close(fig)
        fig = plt.figure(figsize=(9, 6))
        ax = fig.add_subplot(111, projection="3d")
        points = load_capture_arrays(root, scans[0])["points_m"]
        ax.scatter(*points.T, s=1, c=np.linalg.norm(points, axis=1), cmap="viridis")
        ax.set(
            xlabel="Sensor forward X (m)",
            ylabel="Sensor left Y (m)",
            zlabel="Sensor up Z (m)",
            title="Measured first-visible-surface LiDAR returns",
        )
        fig.tight_layout()
        fig.savefig(output / "lidar_scan.png", dpi=140)
        plt.close(fig)
    cameras = [r for r in records if isinstance(r, InspectionCapture) and r.modality == "thermal"]
    for record in cameras:
        image = load_capture_arrays(root, record)["temperature_c"]
        fig, ax = plt.subplots(figsize=(8, 5))
        plot = ax.imshow(image, cmap="inferno", origin="upper")
        fig.colorbar(plot, ax=ax, label="Measured apparent temperature (degC)")
        ax.set(
            title="Virtual radiometric observation / invalid pixels masked",
            xlabel="Pixel column",
            ylabel="Pixel row",
        )
        fig.tight_layout()
        fig.savefig(output / (record.capture_id + ".png"), dpi=140)
        fig.savefig(root / "observations/thermal" / (record.capture_id + ".png"), dpi=140)
        plt.close(fig)
    readings = [r for r in records if not isinstance(r, InspectionCapture)]
    if readings:
        fig, axes = plt.subplots(4, 1, figsize=(11, 10), layout="constrained")
        for ax, kind in zip(axes, ["temperature", "pressure", "operating_load", "vibration_rms"]):
            for sid in sorted({r.sensor_id for r in readings if r.measurement_type == kind}):
                values = sorted(
                    (
                        r
                        for r in readings
                        if r.sensor_id == sid and r.delivery_status != "duplicate"
                    ),
                    key=lambda r: r.acquired_at,
                )
                if not values:
                    continue
                times = [r.acquired_at for r in values]
                ax.plot(times, [r.value for r in values], ".-", markersize=2, label=sid)
            ax.set_ylabel(kind)
            ax.legend(fontsize=7)
            ax.grid(alpha=0.2)
        axes[-1].set_xlabel("UTC simulated acquisition time")
        fig.suptitle("Measured IoT channels (no simulator reference series)")
        fig.savefig(output / "sensor_trends.png", dpi=140)
        plt.close(fig)
    # This separate figure is explicitly simulator geometry context, not a measured scan.
    context_file = root / "evaluation_private/coverage_geometry.npz"
    if context_file.exists():
        with np.load(context_file, allow_pickle=False) as context:
            points = context["vertices_world_m"]
        fig = plt.figure(figsize=(9, 6))
        ax = fig.add_subplot(111, projection="3d")
        ax.scatter(
            *points[:: max(1, len(points) // 4000)].T,
            s=0.5,
            alpha=0.2,
            color="grey",
            label="Simulation geometry context",
        )
        for record in [r for r in records if isinstance(r, InspectionCapture)]:
            matrix = np.asarray(record.sensor_pose.matrix)
            ax.scatter(*matrix[:3, 3], label=record.capture_id)
            ax.quiver(*matrix[:3, 3], *matrix[:3, 0], length=1)
        ax.set(
            xlabel="World X (m)",
            ylabel="World Y (m)",
            zlabel="World Z (m)",
            title="SIMULATION CONTEXT / reported sensor poses (not measured geometry)",
        )
        ax.legend(fontsize=6)
        fig.tight_layout()
        fig.savefig(output / "sensor_coverage.png", dpi=140)
        plt.close(fig)
    return output
