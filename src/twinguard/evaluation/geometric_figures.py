"""Eight measured Phase 3.1 figures; all truth overlays are evaluator-only."""

import json
import shutil
import numpy as np
from twinguard.analytics.pipeline import save_json


def figures(root, heldout=False):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Ellipse, Rectangle

    output = root / "docs/figures/phase3_1"
    output.mkdir(parents=True, exist_ok=True)
    run = root / "experiments/outputs/phase3_1"
    data = json.loads((root / "docs/phase3_1/diagnostic_results.json").read_text())

    def save(fig, name):
        fig.tight_layout()
        fig.savefig(output / name, dpi=180, bbox_inches="tight")
        plt.close(fig)

    amplitudes = ["10", "20", "30", "50"]
    categories = sorted({k for d in data["failures"].values() for k in d["earliest"]})
    fig, ax = plt.subplots(figsize=(11, 5))
    bottom = np.zeros(4)
    for name in categories:
        values = np.array([data["failures"][a]["earliest"].get(name, 0) for a in amplitudes])
        ax.bar(amplitudes, values, bottom=bottom, label=name.replace("_", " "))
        bottom += values
    ax.set(
        xlabel="Injected peak mm (evaluator only)",
        ylabel="Missed trials",
        title="Figure 1: earliest supported limiting stage / reproduced E1",
    )
    ax.legend(fontsize=7, loc="upper right")
    save(fig, "01_failure_stages.png")
    names = list(data["conditions"])
    x = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(11, 5))
    for offset, key in [(-0.18, "actual"), (0.18, "oracle")]:
        values = [data["conditions"][n][key]["raw_mae_mm"] for n in names]
        ax.bar(
            x + offset, [v if v is not None else 0 for v in values], 0.36, label=key + " alignment"
        )
    ax.set_xticks(x, names, rotation=25, ha="right")
    ax.set(
        ylabel="Qualified raw patch MAE mm",
        title="Figure 2: registration isolation (restricted oracle diagnostic)",
    )
    ax.legend()
    ax.text(
        0.01,
        0.97,
        "Degraded: no usable ROI estimates; zero-height bars are missing, not zero error",
        transform=ax.transAxes,
        va="top",
        fontsize=8,
    )
    save(fig, "02_oracle_alignment.png")
    raw = {a: [] for a in ["0", "10", "20", "30", "50"]}
    peak = []
    for path in sorted((run / "baseline-traces").glob("e1-trial-*.json")):
        row = json.loads(path.read_text())
        amp = str(int(row["amplitude_m"] * 1000))
        values = [p for p in row["patches"] if p["inside_roi"] and p["displacement_m"] is not None]
        raw[amp].extend(p["displacement_m"] * 1000 for p in values)
        if values:
            p = max(values, key=lambda p: abs(p["displacement_m"]))
            peak.append(
                {
                    "amplitude_mm": int(amp),
                    "abs_estimate_mm": abs(p["displacement_m"]) * 1000,
                    "effective_threshold_mm": (p["threshold_m"] + 1.5 * p["uncertainty_score_m"])
                    * 1000,
                }
            )
    save_json(
        root / "docs/phase3_1/figure_source_data.json",
        {"raw_roi_displacements_mm": raw, "threshold_peaks": peak, "diagnostic_summary": data},
    )
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.boxplot([raw[a] for a in raw], tick_labels=list(raw), showfliers=False)
    ax.set(
        xlabel="Injected peak mm (evaluator only)",
        ylabel="Raw signed patch displacement mm",
        title="Figure 3: raw measurements, including unqualified-registration diagnostics",
    )
    save(fig, "03_raw_distributions.png")
    fig, ax = plt.subplots(figsize=(9, 5))
    for a in [0, 10, 20, 30, 50]:
        values = [v for v in peak if v["amplitude_mm"] == a]
        ax.scatter(
            [v["effective_threshold_mm"] for v in values],
            [v["abs_estimate_mm"] for v in values],
            label=f"{a} mm",
            s=18,
            alpha=0.6,
        )
    ax.plot([0, 60], [0, 60], "k--", label="significance boundary")
    ax.set(
        xlabel="Original effective threshold mm",
        ylabel="Peak raw absolute ROI estimate mm",
        title="Figure 4: measurement versus uncertainty decision gate",
        xlim=(0, 60),
    )
    ax.legend()
    save(fig, "04_thresholds.png")
    radii = list(data["scales"])
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for a in ["10", "20", "30", "50"]:
        axes[0].plot(
            [float(r) * 1000 for r in radii],
            [data["scales"][r][a]["peak_estimate_mm"] for r in radii],
            marker="o",
            label=a + " mm peak",
        )
    axes[0].set(
        xlabel="Patch radius mm",
        ylabel="Mean measured peak mm",
        title="Oracle-aligned actual scans",
    )
    axes[0].legend()
    axes[1].plot(
        [float(r) * 1000 for r in radii],
        [data["scales"][r]["0"]["region_trials"] / 8 for r in radii],
        marker="o",
    )
    axes[1].set(
        xlabel="Patch radius mm",
        ylabel="Healthy candidate-region frequency",
        ylim=(0, 1),
        title="Original decision/gates, eight healthy acquisitions",
    )
    fig.suptitle("Figure 5: patch attenuation and false-positive consequences")
    save(fig, "05_patch_scales.png")
    first = json.loads(next((run / "baseline-traces").glob("e1-trial-0002.json")).read_text())
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for ax, capture in zip(axes, first["audit"]["captures"]):
        ax.bar(
            ["all hit rays", "valid returns"],
            [capture["all_region_hit_rays"], capture["valid_region_returns"]],
        )
        ax.set(title=capture["capture_id"], ylabel="Actual affected-region samples")
        ax.text(
            0.05,
            0.90,
            f"Occupied fraction {capture['occupied_cell_fraction']:.2f}\nFootprint {capture['sample_footprint_fraction']:.2f}",
            transform=ax.transAxes,
        )
    fig.suptitle(
        "Figure 6: restricted fault-region observability / common fraction "
        + str(round(first["audit"]["common_observed_cell_fraction"], 3))
    )
    save(fig, "06_observability.png")
    if not heldout:
        return output
    report = json.loads((run / "heldout-v1/report.json").read_text())
    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    for ax, level in zip(axes[0], ["L0", "L1", "L2"]):
        for method in ["B3", "B3.1"]:
            d = report["metrics"][method]["fidelity_amplitude"][level]
            ax.plot(
                [10, 20, 30, 50],
                [d[str(a)]["recall"] for a in [10, 20, 30, 50]],
                marker="o",
                label=method,
            )
        ax.set(
            title=level,
            xlabel="Peak displacement mm",
            ylabel="Overall localized recall",
            ylim=(-0.03, 1.03),
        )
        ax.legend()
    for ax, level in zip(axes[1], ["L0", "L1", "L2"]):
        for offset, method in [(-0.18, "B3"), (0.18, "B3.1")]:
            selected = [
                r
                for r in report["rows"]
                if r["method"] == method
                and r["fidelity"] == level
                and r["viewpoint"] in ["same", "changed"]
            ]
            healthy = [r for r in selected if not r["positive"]]
            qualified = [r for r in healthy if r["status"] == "valid"]
            values = [
                sum(r["detected"] for r in healthy) / len(healthy),
                sum(r["status"] != "valid" for r in selected) / len(selected),
                sum(r["detected"] for r in qualified) / len(qualified) if qualified else 0,
            ]
            ax.bar(np.arange(3) + offset, values, 0.36, label=method)
            if not qualified:
                ax.text(2 + offset, 0.03, "n/a", ha="center", fontsize=8, rotation=90)
        ax.set_xticks(np.arange(3), ["all healthy FPR", "abstention", "qualified FPR"], rotation=12)
        ax.set(title=level + " qualification trade-off", ylim=(0, 1.05), ylabel="Fraction")
        ax.legend()
    fig.suptitle(
        "Figure 7: independent same-observation comparison; abstentions retained as misses"
    )
    save(fig, "07_independent_recall.png")
    successes = [
        r for r in report["rows"] if r["method"] == "B3.1" and r["positive"] and r["detected"]
    ]
    failures = [
        r for r in report["rows"] if r["method"] == "B3.1" and r["positive"] and not r["detected"]
    ]
    selected = [successes[0] if successes else failures[0], failures[0]]
    fig = plt.figure(figsize=(13, 9))
    for column, row in enumerate(selected):
        folder = run / "heldout-v1/predictions" / row["case_id"] / "B3.1"
        geometry = json.loads((folder / "geometry.json").read_text())
        points = np.load(folder / "registered_current.npz")["points_m"]
        ax = fig.add_subplot(2, 2, column + 1, projection="3d")
        public = run / "heldout-v1/datasets" / row["case_id"]
        from .geometric_studies import capture_paths, private_context
        from twinguard.analytics.clouds import load_scan
        from twinguard.analytics.config import AnalyticsConfig

        b = load_scan(capture_paths(public)[0], AnalyticsConfig()).processing_world_m
        ax.scatter(
            b[::3, 0], b[::3, 2], b[::3, 1], s=1, c="gray", alpha=0.4, label="measured baseline"
        )
        ax.scatter(
            points[::3, 0],
            points[::3, 2],
            points[::3, 1],
            s=1,
            c="orange",
            alpha=0.4,
            label="registered measured current",
        )
        ax.set(
            xlabel="X m",
            ylabel="Z m",
            zlabel="Y m",
            title=f"{row['case_id']} / {row['fidelity']} / {int(row['amplitude_m'] * 1000)} mm / detected={row['detected']}",
        )
        ax.legend(fontsize=7)
        ax = fig.add_subplot(2, 2, column + 3)
        patches = [
            p
            for p in geometry["patches"]
            if p["status"] == "valid" and p["displacement_m"] is not None
        ]
        if not patches:
            ax.text(
                0.05, 0.95, "No qualified relative displacement", transform=ax.transAxes, va="top"
            )
        centers = np.array([p["center_world_m"] for p in patches])
        if patches:
            scatter = ax.scatter(
                centers[:, 0],
                centers[:, 2],
                c=[p["displacement_m"] * 1000 for p in patches],
                s=12,
                cmap="coolwarm",
                vmin=-20,
                vmax=20,
            )
            fig.colorbar(scatter, ax=ax, label="Measured relative displacement mm")
        _, _, fault = private_context(public)
        ax.add_patch(
            Ellipse(
                (fault["center_local_m"][0], fault["center_local_m"][2] + 0.35),
                2 * fault["extent_m"][0],
                2 * fault["extent_m"][2],
                fill=False,
                color="black",
                linestyle="--",
                label="EVALUATOR ONLY fault support",
            )
        )
        for region in geometry["regions"]:
            low, high = np.array(region["bounds_world_m"])
            ax.add_patch(
                Rectangle(
                    (low[0], low[2]),
                    max(high[0] - low[0], 0.02),
                    max(high[2] - low[2], 0.02),
                    fill=False,
                    color="green",
                )
            )
        ax.set(
            xlim=(-1, 1),
            ylim=(0.35, 2.75),
            xlabel="X m",
            ylabel="Z m",
            title="Actual patches/regions; dashed truth is evaluator-only",
        )
        ax.legend(fontsize=7)
    fig.suptitle("Figure 8: measured successful/failed examples; selection is evaluator-only")
    save(fig, "08_examples.png")
    for p in output.glob("*.png"):
        shutil.copy2(p, run / "heldout-v1" / p.name)
    return output
