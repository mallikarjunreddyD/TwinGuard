"""Scientific result plots. Predictions and post-inference metrics are distinguished."""

from pathlib import Path
import json
import numpy as np


def experiment_figures(root: Path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    report = json.loads((root / "report.json").read_text())
    figures = root / "figures"
    figures.mkdir(exist_ok=True)
    if report["experiment_id"] == "E1":
        fig, axes = plt.subplots(1, 3, figsize=(15, 4), layout="constrained")
        methods = ["B1", "B2", "B3"]
        colors = ["tab:grey", "tab:orange", "tab:blue"]
        for method, color in zip(methods, colors):
            rows = [
                r
                for r in report["rows"]
                if r["method"] == method and r.get("fault_kind", "water_wall") != "support"
            ]
            amplitudes = sorted({r["amplitude_m"] for r in rows if r["positive"]})
            recall = [
                sum(r["detected"] for r in rows if r["amplitude_m"] == a and r["positive"])
                / sum(r["amplitude_m"] == a and r["positive"] for r in rows)
                for a in amplitudes
            ]
            axes[0].plot(np.array(amplitudes) * 1000, recall, "o-", label=method, color=color)
        axes[0].set(
            xlabel="Injected amplitude (mm), evaluator only",
            ylabel="Localized trial recall",
            ylim=(-0.02, 1.02),
            title="Held-out sensitivity; failures retained",
        )
        axes[0].legend()
        axes[1].bar(
            methods, [report["metrics"][m]["false_positive_rate"] for m in methods], color=colors
        )
        axes[1].set(
            ylabel="Healthy-control false-positive fraction",
            ylim=(0, 1),
            title="Same underlying healthy observations",
        )
        axes[2].bar(
            methods,
            [report["metrics"][m]["translation_error_mm_mean"] for m in methods],
            color=colors,
        )
        axes[2].set(
            ylabel="Transform translation error (mm)",
            title="Registration metric, not displacement accuracy",
        )
        fig.savefig(figures / "E1_comparison.png", dpi=150)
        plt.close(fig)
        predictions = Path(report.get("prediction_directory", root / "predictions"))
        if not predictions.is_absolute() and not predictions.exists():
            predictions = root / predictions
        paths = list(predictions.glob("*/B3/patches.npz"))
        # Deterministic first available measured candidate; never choose by true error.
        selected = next(
            (p for p in sorted(paths) if np.load(p, allow_pickle=False)["significant"].any()),
            paths[0] if paths else None,
        )
        if selected:
            with np.load(selected, allow_pickle=False) as data:
                centers = data["centers_m"]
                values = data["displacement_m"] * 1000
                uncertainty = data["uncertainty_score_m"] * 1000
                valid = data["valid"]
                significant = data["significant"]
            fig, axes = plt.subplots(1, 3, figsize=(15, 5), layout="constrained")
            for ax, field, title in zip(
                axes,
                [values, uncertainty, np.where(valid, significant.astype(float), np.nan)],
                [
                    "Measured normal displacement (mm)",
                    "Estimated variability score (mm)",
                    "Engineering screening (1=candidate)",
                ],
            ):
                ax.scatter(
                    centers[~valid, 0], centers[~valid, 2], s=5, c="lightgrey", label="unqualified"
                )
                plot = ax.scatter(
                    centers[valid, 0], centers[valid, 2], c=field[valid], s=14, cmap="coolwarm"
                )
                fig.colorbar(plot, ax=ax)
                ax.set(xlabel="Accepted world X (m)", ylabel="Accepted world Z (m)", title=title)
                ax.set_aspect("equal")
            fig.suptitle("B3 predictions only / no fault mask or current simulator mesh")
            fig.savefig(figures / "E1_patch_quality.png", dpi=150)
            plt.close(fig)
        audits = list(predictions.glob("*/evaluation_private/observability.json"))
        if audits:
            audit = json.loads(sorted(audits)[0].read_text())
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.bar(
                [str(c["time_s"]) for c in audit["captures"]],
                [c["occupied_cell_fraction"] for c in audit["captures"]],
            )
            ax.set(
                xlabel="Acquisition time (s)",
                ylabel="True region occupied-cell fraction",
                title="RESTRICTED evaluator observability audit / not detector input",
                ylim=(0, 1),
            )
            fig.tight_layout()
            fig.savefig(figures / "E1_observability.png", dpi=150)
            plt.close(fig)
    else:
        methods = ["static", "conditioned", "conditioned_quality"]
        groups = ["N1", "N2", "F1", "F2", "F3", "F4"]
        fig, axes = plt.subplots(1, 2, figsize=(13, 5), layout="constrained")
        x = np.arange(len(groups))
        width = 0.25
        for i, method in enumerate(methods):
            axes[0].bar(
                x + (i - 1) * width,
                [
                    report["metrics"][g]["operating"][method]["mean_false_positive_rate"]
                    for g in groups
                ],
                width,
                label=method,
            )
            axes[1].bar(
                x + (i - 1) * width,
                [
                    report["metrics"][g]["operating"][method]["mean_inconclusive_fraction"]
                    for g in groups
                ],
                width,
                label=method,
            )
        for ax in axes:
            ax.set_xticks(x, groups)
            ax.set_ylim(0, 1)
            ax.legend(fontsize=7)
        axes[0].set(
            title="Measurement-level false positives by scenario group",
            ylabel="Fraction of negative observations",
        )
        axes[1].set(title="Qualified abstentions / missing context", ylabel="Inconclusive fraction")
        fig.savefig(figures / "E2_comparison.png", dpi=150)
        plt.close(fig)
        # Display held-out normal load-transition residuals, without any true expected series.
        row = next(r for r in report["rows"] if r["group"] == "N2")
        folder = root / "predictions" / row["case_id"]
        fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True, layout="constrained")
        for method in methods[:2]:
            results = json.loads((folder / f"operating-{method}.json").read_text())
            values = [
                p
                for p in results
                if p["sensor_id"] == "temperature-01" and p["residual"] is not None
            ]
            from datetime import datetime

            times = [
                datetime.fromisoformat(p["acquired_at"].replace("Z", "+00:00")) for p in values
            ]
            axes[0].plot(
                times,
                [p["observed_value"] for p in values],
                ".",
                markersize=2,
                label="measured " + method,
            )
            axes[0].plot(
                times, [p["estimated_reference"] for p in values], label="calibrated " + method
            )
            axes[1].plot(times, [p["residual"] for p in values], label=method)
        axes[0].set(
            ylabel="Measured/model temperature (degC)",
            title="Held-out normal load increase / public observations only",
        )
        axes[1].set(ylabel="Residual (degC)", xlabel="UTC acquisition time")
        axes[0].legend()
        axes[1].legend()
        fig.savefig(figures / "E2_operating_residuals.png", dpi=150)
        plt.close(fig)
        positive = next(r for r in report["rows"] if r["group"] == "F1")
        paths = sorted((root / "predictions" / positive["case_id"] / "conditioned").glob("*.npz"))
        chosen = next(
            (p for p in paths if np.load(p, allow_pickle=False)["candidate_mask"].any()), paths[0]
        )
        with np.load(chosen, allow_pickle=False) as data:
            residual = data["residual_c"]
            mask = data["candidate_mask"]
            valid = data["quantitative_mask"]
        fig, axes = plt.subplots(1, 3, figsize=(13, 4), layout="constrained")
        image = axes[0].imshow(residual, cmap="coolwarm")
        fig.colorbar(image, ax=axes[0], label="Apparent residual (degC)")
        axes[0].set_title("Calibrated thermal residual")
        axes[1].imshow(mask, cmap="Greys")
        axes[1].set_title("Predicted candidate pixels")
        axes[2].imshow(valid, cmap="Greys")
        axes[2].set_title("Quantitative valid mask")
        fig.suptitle("Thermal predictions / no hidden temperature overlay")
        fig.savefig(figures / "E2_thermal_residuals.png", dpi=150)
        plt.close(fig)
    return figures
