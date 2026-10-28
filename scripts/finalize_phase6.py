"""Post-seal E5 evaluator/report; never imported by operational planning."""

from pathlib import Path
import json
from datetime import datetime, timezone
import shutil
import numpy as np
from twinguard.evaluation.analytics import verify_seal
from twinguard.inspection.observations import load_config
from twinguard.inspection.coverage import ReferenceSurface
from twinguard.analytics.pipeline import save_json

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "experiments/outputs/phase6-E5-recovered"
DEST = ROOT / "docs/phase6"
FIG = ROOT / "docs/figures/phase6"
METHODS = ["P0", "P1", "P2", "P3"]


def strict_detected(geometry, fault):
    if not fault or geometry.get("status") != "valid":
        return False
    configuration = fault["configuration"]
    center = np.asarray(configuration["center_local_m"]) + [0, 0, 0.35]
    extent = np.asarray(configuration["extent_m"])
    patches = {p["patch_id"]: p for p in geometry.get("patches", [])}
    for region in geometry.get("regions", []):
        if region.get("asset_id") != "BW-01" or region.get("association_status") != "associated":
            continue
        for ident in region["patch_ids"]:
            p = patches.get(ident)
            if (
                p
                and p["status"] == "valid"
                and p.get("significant") is True
                and p.get("calibration_support", 0) >= 10
            ):
                point = np.asarray(p["center_world_m"])
                if sum(((point[j] - center[j]) / extent[j]) ** 2 for j in (0, 2)) <= 1:
                    return True
    return False


def main():
    if not (RUN / "report.json").exists():
        raise ValueError("Full E5 not complete")
    DEST.mkdir(exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    config = load_config(ROOT / "configs/inspection/planner.yaml")
    surface = ReferenceSurface(ROOT / config.reference_path, config.reference_sha256, config.cell_m)
    primary = []
    seal_checks = []
    freeze = []
    scenarios = {}
    for shard in sorted(RUN.glob("shard-*")):
        freeze.append(json.loads((shard / "freeze.json").read_text()))
        for raw in json.loads((shard / "trial_table.json").read_text()):
            trial = shard / f"{raw['scenario']}-{raw['seed']}"
            work = trial / raw["method"]
            verify_seal(work)
            snapshot = json.loads((trial / "initial-snapshot.json").read_text())
            initial = json.loads((trial / "initial-analysis/B3.1/geometry.json").read_text())
            frozen = json.loads((work / "plan.json").read_text())
            results = json.loads((work / "results.json").read_text())
            # Labels opened strictly after this method's result manifest has been verified.
            truth = json.loads((trial / "evaluation_private/truth.json").read_text())
            fault = next(
                (
                    f
                    for f in truth["fault_states"]
                    if f["category"] == "localized_geometric_deformation" and f["present"]
                ),
                None,
            )
            detected = any(strict_detected(r.get("analysis", {}), fault) for r in results)
            initial_detected = strict_detected(initial, fault)
            init_observed = {i for c in snapshot["coverage"] for i in c["observed_cells"]}
            init_qualified = {i for c in snapshot["coverage"] for i in c["qualified_cells"]}
            actual_observed = set(init_observed)
            actual_qualified = set(init_qualified)
            pred_visible = set()
            pred_usable = set()
            valid_returns = 0
            quality_status = []
            for result in results:
                cov = result.get("coverage", {})
                actual_observed.update(cov.get("observed_cells", []))
                actual_qualified.update(cov.get("qualified_cells", []))
                candidate = next(
                    v for v in frozen["candidates"] if v["viewpoint_id"] == result["viewpoint_id"]
                )
                pred_visible.update(candidate["predicted_visible_cells"])
                pred_usable.update(candidate["predicted_usable_cells"])
                quality_status.append(
                    result.get("analysis", result.get("thermal", {})).get("status")
                )
            for path in work.glob("view-*/observations/lidar/*.json"):
                record = json.loads(path.read_text())
                valid_returns += record["quality_indicators"].get("valid_returns", 0)
            area = surface.area_of(actual_observed - init_observed)
            new_qualified = surface.area_of(actual_qualified - init_qualified)
            matched_pred = surface.area_of(pred_visible - init_observed)
            pending_reviews = frozen["approval_status"] == "pending_operator_review"
            missing_review = (
                any(a["critical_process"] for a in snapshot["assets"]) and not pending_reviews
            )
            current_status = quality_status[-1] if quality_status else initial["status"]
            row = {
                **raw,
                "localized_detected": detected,
                "initial_localized_detected": initial_detected,
                "additional_localized_discovery": detected and not initial_detected,
                "cumulative_localized_detected": detected or initial_detected,
                "actual_new_area_m2": area,
                "qualified_new_area_m2": new_qualified,
                "matched_predicted_visible_new_area_m2": matched_pred,
                "matched_visibility_error_m2": area - matched_pred,
                "predicted_usable_new_area_m2": surface.area_of(pred_usable - init_qualified),
                "actual_final_qualified_area_m2": surface.area_of(actual_qualified),
                "new_view_positive": any(
                    r.get("analysis", {}).get("significant") is True
                    and r["analysis"]["status"] == "valid"
                    for r in results
                ),
                "valid_lidar_returns": valid_returns,
                "return_density_proxy_per_m2": valid_returns
                / max(surface.area_of(actual_observed), 1e-12)
                if valid_returns
                else None,
                "final_geometry_inconclusive": current_status != "valid",
                "critical_review_omitted": missing_review,
                "artifact_directory": str(work.relative_to(ROOT)),
            }
            primary.append(row)
            acquisition_files = list(work.glob("view-*/manifest.json"))
            frozen_before = all(
                (work / "plan.json").stat().st_mtime_ns <= p.stat().st_mtime_ns
                for p in acquisition_files
            )
            budget = (
                raw["estimated_duration_s"] <= raw["budget_s"] + 1e-8
                and raw["views"] <= raw["budget_views"]
            )
            seal_checks.append(
                {
                    "trial": trial.name,
                    "method": raw["method"],
                    "verified_result_seal": True,
                    "plan_file_precedes_acquisition_files": frozen_before,
                    "budget_compliant": budget,
                    "critical_review_omitted": missing_review,
                }
            )
            scenarios.setdefault(raw["scenario"], []).append(row)
    if len(primary) != 2160:
        raise ValueError(f"Expected 2160 method runs, got {len(primary)}")
    for sid, rows in scenarios.items():
        for seed in {r["seed"] for r in rows}:
            paired = [r for r in rows if r["seed"] == seed]
            if (
                len(paired) != 4
                or len({r["snapshot_hash"] for r in paired}) != 1
                or len({r["candidate_hash"] for r in paired}) != 1
                or len({(r["budget_s"], r["budget_views"]) for r in paired}) != 1
            ):
                raise ValueError("Unpaired trial")
    summary = {}
    for method in METHODS:
        rows = [r for r in primary if r["method"] == method]
        positive = [r for r in rows if r["geometric_positive"]]
        negative = [r for r in rows if not r["geometric_positive"]]
        summary[method] = {
            "runs": len(rows),
            "views": sum(r["views"] for r in rows),
            "geometric_positive_trials": len(positive),
            "localized_new_scan_detections": sum(r["localized_detected"] for r in positive),
            "initial_detections": sum(r["initial_localized_detected"] for r in positive),
            "additional_discoveries": sum(r["additional_localized_discovery"] for r in positive),
            "cumulative_detections": sum(r["cumulative_localized_detected"] for r in positive),
            "new_positive_without_injected_geometric_fault": sum(
                r["new_view_positive"] for r in negative
            ),
            "healthy_control_positive_trials": sum(
                r["new_view_positive"]
                for r in rows
                if r["scenario"]
                in ("E5-S01", "E5-S02", "E5-S12", "E5-S13", "E5-S14", "E5-S16", "E5-S18")
            ),
            "healthy_control_trials": 210,
            "negative_trials": len(negative),
            "actual_new_area_mean_m2": float(np.mean([r["actual_new_area_m2"] for r in rows])),
            "qualified_new_area_mean_m2": float(
                np.mean([r["qualified_new_area_m2"] for r in rows])
            ),
            "final_inconclusive_trials": sum(r["final_geometry_inconclusive"] for r in rows),
            "planning_mean_s": float(np.mean([r["planning_runtime_s"] for r in rows])),
            "planning_p95_s": float(np.quantile([r["planning_runtime_s"] for r in rows], 0.95)),
            "estimated_duration_mean_s": float(np.mean([r["estimated_duration_s"] for r in rows])),
            "inspection_data_total_bytes": sum(r["data_bytes"] for r in rows),
            "by_amplitude_mm": {
                str(mm): {
                    "detected": sum(
                        r["localized_detected"]
                        for r in positive
                        if round(r["amplitude_m"] * 1000) == mm
                    ),
                    "trials": sum(round(r["amplitude_m"] * 1000) == mm for r in positive),
                }
                for mm in (10, 20, 30, 50)
            },
        }
    # Pair at independent seed level, averaging repeated scenario conditions within a seed.
    seeds = sorted({r["seed"] for r in primary})
    rng = np.random.default_rng(12345)
    comparisons = {}
    for comparator in ("P0", "P1", "P2"):
        comparisons[comparator] = {}
        for metric in (
            "qualified_new_area_m2",
            "actual_new_area_m2",
            "localized_detected",
            "final_geometry_inconclusive",
        ):
            differences = []
            for seed in seeds:
                a = [r for r in primary if r["seed"] == seed and r["method"] == "P3"]
                b = [r for r in primary if r["seed"] == seed and r["method"] == comparator]
                if metric == "localized_detected":
                    a = [r for r in a if r["geometric_positive"]]
                    b = [r for r in b if r["geometric_positive"]]
                differences.append(
                    float(np.mean([r[metric] for r in a]) - np.mean([r[metric] for r in b]))
                )
            values = np.array(differences)
            boot = values[rng.integers(0, len(values), (2000, len(values)))].mean(axis=1)
            comparisons[comparator][metric] = {
                "P3_minus_comparator_mean": float(values.mean()),
                "seed_cluster_bootstrap_95": np.quantile(boot, [0.025, 0.975]).tolist(),
                "independent_seeds": len(seeds),
            }
    platform = json.loads((ROOT / "experiments/outputs/phase6-platform/report.json").read_text())
    demo = json.loads(
        (ROOT / "experiments/outputs/phase6-platform-reinspection/report.json").read_text()
    )
    report = {
        "experiment_id": "E5",
        "status": "executed",
        "independent_heldout_seeds": 30,
        "scenario_classes": 18,
        "paired_trials": 540,
        "method_runs": 2160,
        "summary": summary,
        "paired_seed_comparisons": comparisons,
        "seal_checks_pass": all(
            v["verified_result_seal"]
            and v["plan_file_precedes_acquisition_files"]
            and v["budget_compliant"]
            and not v["critical_review_omitted"]
            for v in seal_checks
        ),
        "platform": {k: v for k, v in platform.items() if k != "planning_jobs"},
        "closed_loop_platform": demo,
        "limitations": [
            "Nominal healthy-recent inputs retain only actual partial qualified coverage; no entire-plant sufficient-coverage claim",
            "The frozen B3.1 calibration supports BW-01, limiting meaningful multi-asset geometric competition",
            "S06 uses partial FOV and existing self-occlusion, not a separately injected external occluder",
            "S15 uses L2 abstention; it does not itself execute a viable new L2 view",
            "Strict localized detection uses qualified significant patch centers inside the true ellipse only after result sealing; original raw bounding-box overlap metric retained separately",
            "Mission durations are geometric simulation proxies; no physical calibration/flight claim",
            "Full acquisition ablations are not executed; primary comparison remains frozen and paired",
        ],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    resource_path = ROOT / "experiments/outputs/phase6-resource-observations/processes.json"
    if resource_path.exists():
        resource = json.loads(resource_path.read_text())
        pids = {v["pid"] for v in resource["processes"]}
        workers = [v for v in resource["processes"] if v["parent_pid"] in pids]
        report["resource_observations"] = {
            "cumulative_trial_worker_cpu_seconds_lower_bound": sum(
                v["user_cpu_s"] + v["system_cpu_s"] for v in workers
            ),
            "scope": resource["scope"],
            "observed_trial_worker_peak_rss_mib": max(v["observed_peak_rss_kib"] for v in workers)
            / 1024,
        }
    report["platform"]["test_input_scope"] = (
        "Two sets of 30 scheduled replay cases using one recorded synthetic pressure measurement and synthetic test IDs; not independent physical acquisitions"
    )
    save_json(DEST / "results.json", report)
    save_json(DEST / "trial_table.json", primary)
    save_json(DEST / "integrity_checks.json", seal_checks)
    save_json(DEST / "freeze.json", freeze)
    figures(surface, primary, scenarios, summary)
    probe_path = ROOT / "docs/phase6/L2_probes.json"
    if probe_path.exists():
        import matplotlib.pyplot as plt

        probes = json.loads(probe_path.read_text())["rows"]
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar(
            ["Actual alternate L2 scans", "Qualified patches", "Positive geometric evidence"],
            [
                len(probes),
                sum(v["qualified_patches"] for v in probes),
                sum(v["geometric_positive_evidence"] for v in probes),
            ],
            color=["#64748b", "#22a99e", "#8462cd"],
        )
        ax.set_title("Rejected alternate-view diagnostic: L2 limitation persists")
        ax.set_ylabel("Actual measured count (30 independent seeds)")
        fig.tight_layout()
        fig.savefig(FIG / "E5-9.png", dpi=160)
        plt.close(fig)
    source = ROOT / "experiments/outputs/phase6-platform-final/E5-10-dashboard.png"
    if not source.exists():
        source = ROOT / "experiments/outputs/phase6-platform/E5-10-dashboard.png"
    shutil.copy2(source, FIG / "E5-10-dashboard.png")
    print(
        json.dumps(
            {"summary": summary, "all_integrity_checks": report["seal_checks_pass"]}, indent=2
        ),
        flush=True,
    )


def figures(surface, rows, scenarios, summary):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = ["#64748b", "#22a99e", "#db9839", "#8462cd"]
    example = next(r for r in rows if r["scenario"] == "E5-S03" and r["method"] == "P3")
    work = ROOT / example["artifact_directory"]
    plan = json.loads((work / "plan.json").read_text())
    trial = work.parent
    snap = json.loads((trial / "initial-snapshot.json").read_text())

    def scene(ax):
        points = surface.centers
        ax.scatter(points[:, 0], points[:, 1], points[:, 2], s=1, c="#aeb9c4", alpha=0.3)
        ax.set_xlabel("world X (m)")
        ax.set_ylabel("world Y (m)")
        ax.set_zlabel("world Z (m)")
        ax.view_init(22, -65)

    for num, title, selected_only in [
        (1, "Accepted map and candidate positions", False),
        (4, "Recommended static inspection sequence", True),
    ]:
        fig = plt.figure(figsize=(9, 6))
        ax = fig.add_subplot(projection="3d")
        scene(ax)
        selected = {s["viewpoint_id"] for s in plan["steps"]}
        vs = [v for v in plan["candidates"] if not selected_only or v["viewpoint_id"] in selected]
        for v in vs:
            p = np.array(v["planned_pose"]["matrix"])[:3, 3]
            ax.scatter(
                *p,
                s=30 if v["viewpoint_id"] in selected else 6,
                c="#32bbce"
                if v["viewpoint_id"] in selected
                else "#df6c6c"
                if v["feasibility"]["status"] == "infeasible"
                else "#92a0ab",
            )
        if selected_only:
            pts = [
                np.array(
                    next(v for v in vs if v["viewpoint_id"] == s["viewpoint_id"])["planned_pose"][
                        "matrix"
                    ]
                )[:3, 3]
                for s in plan["steps"]
            ]
            if pts:
                ax.plot(*np.asarray(pts).T, c="#32bbce", label="Static recommendation, not flight")
        ax.set_title(title)
        fig.tight_layout()
        fig.savefig(FIG / f"E5-{num}.png", dpi=160)
        plt.close(fig)
    for num, title, key, ylabel in [
        (
            2,
            "Actual qualified new area under paired budgets",
            "qualified_new_area_m2",
            "mean qualified new area (m²)",
        ),
        (
            7,
            "Strict localized new-scan detection recall",
            "localized_detected",
            "fraction of geometric-positive trials",
        ),
        (
            9,
            "L2 remains unqualified: actual initial acquisitions",
            "final_geometry_inconclusive",
            "fraction inconclusive / unavailable",
        ),
    ]:
        fig, ax = plt.subplots(figsize=(8, 4))
        data = rows if num != 9 else [r for r in rows if r["scenario"] == "E5-S05"]
        values = [
            np.mean(
                [r[key] for r in data if r["method"] == m and (num != 7 or r["geometric_positive"])]
            )
            for m in METHODS
        ]
        ax.bar(METHODS, values, color=colors)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        fig.tight_layout()
        fig.savefig(FIG / f"E5-{num}.png", dpi=160)
        plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 4))
    terms = list(plan["priorities"][0]["terms"])
    bottom = np.zeros(len(plan["priorities"]))
    for term in terms:
        values = (
            np.array([v["terms"][term] for v in plan["priorities"]])
            * load_config(ROOT / "configs/inspection/planner.yaml").priority_weights[term]
        )
        ax.bar([v["asset_id"] for v in plan["priorities"]], values, bottom=bottom, label=term)
        bottom += values
    ax.set_ylabel("weighted engineering need")
    ax.set_title("Risk and evidence priority contributions")
    ax.legend(ncol=3, fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "E5-3.png", dpi=160)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(7, 5))
    for method, color in zip(METHODS, colors):
        group = [r for r in rows if r["method"] == method]
        ax.scatter(
            [r["matched_predicted_visible_new_area_m2"] for r in group],
            [r["actual_new_area_m2"] for r in group],
            s=8,
            alpha=0.3,
            label=method,
            c=color,
        )
    limit = max(r["matched_predicted_visible_new_area_m2"] for r in rows)
    ax.plot([0, limit], [0, limit], ls="--", c="black")
    ax.set_xlabel("predicted new visible area (m²)")
    ax.set_ylabel("actual associated new area (m²)")
    ax.legend()
    ax.set_title("Prediction vs acquisition: same observed-history denominator")
    fig.tight_layout()
    fig.savefig(FIG / "E5-5.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    stages = [snap] + [json.loads(p.read_text()) for p in sorted(work.glob("snapshot-*.json"))]
    for aid in ("BW-01", "DR-01"):
        axes[0].plot(
            range(len(stages)),
            [
                surface.area_of(
                    {
                        i
                        for c in st["coverage"]
                        if c["asset_id"] == aid
                        for i in c["qualified_cells"]
                    }
                )
                for st in stages
            ],
            marker="o",
            label=aid,
        )
    axes[0].set_xlabel("public update cycle")
    axes[0].set_ylabel("qualified area union (m²)")
    axes[0].legend()
    axes[0].set_title("Actual closed-loop qualification")
    for method, color in zip(METHODS, colors):
        group = [r for r in rows if r["method"] == method]
        axes[1].scatter(
            [r["estimated_duration_s"] for r in group],
            [r["qualified_new_area_m2"] for r in group],
            s=6,
            alpha=0.25,
            label=method,
            c=color,
        )
    axes[1].set_xlabel("mission time proxy (s)")
    axes[1].set_ylabel("qualified new area (m²)")
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(FIG / "E5-6.png", dpi=160)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 4))
    for method, color in zip(METHODS, colors):
        group = [r for r in rows if r["method"] == method]
        ax.scatter(
            np.mean([r["estimated_duration_s"] for r in group]),
            np.mean([r["qualified_new_area_m2"] for r in group]),
            s=100,
            c=color,
            label=method,
        )
    ax.set_xlabel("mean mission-duration proxy (s)")
    ax.set_ylabel("mean actual qualified new area (m²)")
    ax.legend()
    ax.set_title("Actual qualification versus estimated inspection effort")
    fig.tight_layout()
    fig.savefig(FIG / "E5-8.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
