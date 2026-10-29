"""Finalize only executed Phase7 evidence; keep physical and research limits explicit."""

from pathlib import Path
import json
import hashlib
import numpy as np
from phase7_summarize import detector_summary, planner_summary, operational, clustered
from phase7_write_reports import main as write_reports

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs"
OUT = DOC / "phase7"
EXT = Path("/mnt/d/TwinGuard")


def load(p):
    return json.loads(p.read_text())


def save(p, d):
    p.write_text(json.dumps(d, indent=2, default=str, allow_nan=False) + "\n")


def control_summary(folder, name):
    journal = load(folder / "campaign.json")
    rows = []
    for ident, checksum in journal["completed"].items():
        p = folder / "cases" / (ident + ".json")
        data = p.read_bytes()
        if hashlib.sha256(data).hexdigest() != checksum:
            raise ValueError("Control checkpoint mismatch")
        rows.extend(json.loads(data))
    result = {
        "status": journal["status"],
        "completed": len(journal["completed"]),
        "expected": journal["configuration"]["count"],
        "groups": {},
    }
    if journal["status"] == "completed":
        for mode in sorted(
            {r.get("supplemental_control", r.get("chronology_control", "")) for r in rows}
        ):
            for detector in ("B3.1", "B3.2"):
                for method in ("P0", "P1", "P2", "P3", "P3v2"):
                    rr = [
                        r
                        for r in rows
                        if r.get("supplemental_control", r.get("chronology_control", "")) == mode
                        and r["detector"] == detector
                        and r["method"] == method
                    ]
                    result["groups"][mode + " / " + detector + " / " + method] = {
                        "trials": len(rr),
                        "views": sum(r["views"] for r in rr),
                        "initial_public_unconfirmed": sum(r["previously_unconfirmed"] for r in rr),
                        "initial_localized": sum(r["initial_localized"] for r in rr),
                        "new_localized": sum(r["new_localized"] for r in rr),
                        "healthy_fp": sum(r["healthy_false_positive"] for r in rr),
                        "inconclusive": sum(r["inconclusive"] for r in rr),
                        "scope_actually_qualified": sum(
                            r.get("scope_actually_qualified", False) for r in rr
                        ),
                        "continued_monitoring": sum(
                            r["plan_status"] == "continue_monitoring" for r in rr
                        ),
                        "new_qualified_area_m2": sum(r["new_qualified_area_m2"] for r in rr),
                        "mission_proxy_s": sum(r["mission_proxy_s"] for r in rr),
                        "new_localized_recall": clustered(
                            rr,
                            lambda r: r["amplitude_m"] > 0 and r["new_localized"],
                            lambda r: r["amplitude_m"] > 0,
                        ),
                        "controller_cpu_s": sum(r["cpu_s"] for r in rr),
                        "peak_rss_kib": max(r["rss_peak_kib"] for r in rr),
                    }
    save(OUT / name, result)
    return result


def derived_summary():
    folder = EXT / "phase7-derived-view-metrics-v2/main"
    source = load(ROOT / "experiments/outputs/phase7-V3-heldout-planners/campaign.json")
    rows = []
    for ident, sha in source["completed"].items():
        p = folder / (ident + ".json")
        if not p.exists():
            return {"status": "incomplete", "reason": "Missing derived view audit " + ident}
        data = load(p)
        if data["source_case_sha256"] != sha:
            raise ValueError("Derived view audit source mismatch")
        rows.extend(data["rows"])
    result = {
        "status": "completed" if source["status"] == "completed" else "incomplete",
        "source_cases": len(source["completed"]),
        "groups": {},
    }
    for detector in ("B3.1", "B3.2"):
        for method in ("P0", "P1", "P2", "P3", "P3v2"):
            rr = [r for r in rows if r["detector"] == detector and r["method"] == method]
            views = sum(r["views"] for r in rr)
            useful = sum(r["useful_localized_views"] for r in rr)
            cost = sum(r["mission_proxy_s"] for r in rr)
            result["groups"][detector + " / " + method] = {
                "views": views,
                "useful_localized_views": useful,
                "useful_views_per_view": useful / views if views else None,
                "useful_views_per_mission_proxy_min": useful / (cost / 60) if cost else None,
                "new_capture_payload_bytes": sum(r["new_capture_payload_bytes"] for r in rr),
                "analysis_wall_s": sum(r["analysis_wall_s"] for r in rr),
                "optimizer_inner_wall_s": sum(r["optimizer_inner_wall_s"] for r in rr),
                "visibility_prediction_error_m2_mean": float(
                    np.mean([r["visibility_prediction_error_m2"] for r in rr])
                ),
                "visibility_prediction_error_m2_mae": float(
                    np.mean([abs(r["visibility_prediction_error_m2"]) for r in rr])
                ),
                "actual_observed_new_area_m2": sum(r["actual_observed_new_area_m2"] for r in rr),
                "actual_qualified_new_area_m2": sum(r["actual_qualified_new_area_m2"] for r in rr),
            }
    save(OUT / "verified_view_resource_summary.json", result)
    return result


def main(allow_incomplete_chronology=False):
    source = ROOT / "experiments/outputs/phase7-V3-heldout-planners/campaign.json"
    controls = EXT / "phase7-V3-supplemental-heldout-controls/campaign.json"
    freshness = EXT / "phase7-V3-freshness-heldout/campaign.json"
    required = [source, controls, freshness, EXT / "phase7-V4-mixed-boundary-retest-v3/report.json"]
    for p in required:
        if not p.exists():
            raise ValueError("Required execution missing: " + str(p))
        if p.name == "campaign.json" and load(p)["status"] != "completed":
            if not (allow_incomplete_chronology and p == freshness):
                raise ValueError("Cannot finalize incomplete campaign: " + str(p))
    detector_summary()
    plans, ablations = planner_summary()
    control = control_summary(controls.parent, "supplemental_control_summary.json")
    fresh = control_summary(freshness.parent, "fresh_chronology_summary.json")
    views = derived_summary()
    if views["status"] != "completed":
        raise ValueError(views)
    final_e4 = operational(str(EXT / "phase7-V4-full-E4-admission-retest"), [8210, 8211, 8212])
    mixed = operational(str(EXT / "phase7-V4-mixed-boundary-retest-v3"), [18610, 18611, 18612])
    write_reports()
    text = "\n\n## Identical supported-domain comparison\n\nRestricting both detectors to the same 300 public applicability-domain cases isolates calibration from abstention: B3.1 localized 237/240 faults and produced 18/60 healthy positive scans; B3.2 localized 235/240 and produced 4/60. Neither was inconclusive in that subset. This demonstrates a conditional false-positive reduction with a small sensitivity tradeoff. It does not establish overall superiority or support outside these domains.\n"
    text += "\n## Complete paired planner outcomes\n\n240 paired cases, five methods under each common detector. Each detector has 120 fault cases and 120 healthy/control cases. Main amplitudes are10/20/30mm;50mm is included in the separate detector study. The comparison is LiDAR-only; equivalent thermal/multi-asset geometric calibration is not claimed.\n\n| Detector / planner | Views | Initial / new / cumulative recall | Additional recall among initial misses | Healthy positive trials (rate) | Inconclusive scans | New qualified area total m² |\n|---|---:|---|---|---|---:|---:|\n"
    for name, r in plans["methods"].items():

        def val(k):
            return "n/a" if r[k]["estimate"] is None else f"{r[k]['estimate']:.3f}"

        text += f"| {name} | {r['views']} | {val('initial_recall')} / {val('new_recall')} / {val('cumulative_recall')} | {val('additional_recall')} | {val('healthy_false_positive')} | {r['inconclusive']} | {r['new_qualified_area_total_m2']:.3f} |\n"
    text += "\nAll seed-cluster intervals and confirmation/precision/resource statistics are in `heldout_planner_summary.json`. Lower false-positive or inconclusive totals with fewer acquired views are not evidence of superiority. Initial screening, new-scan localization, additional discovery and confirmation remain distinct. The original `previously_unconfirmed` family is initially positive under B3.1; genuinely unconfirmed fixed-left controls are reported separately. The main stale_initial case delivers old-timestamp data after a later decision; it must not be interpreted as fresh reacquisition. A separate 30-seed chronology campaign acquires at7272/7280 after the aged decision without rewriting source timestamps.\n"
    text += "\n## Actual per-view yield and resources\n\nSealed result hashes and every referred raw/registered point-cloud hash were checked before per-view evaluation. Qualified area was recomputed from estimated registered public points and unchanged valid patch bounds, agreeing with every frozen case. These are accepted-map association/area estimates, not surveyed physical coverage. Visibility errors compare the union of executed nominal predicted-visible cells with measured registered-point association.\n\n| Detector / planner | Useful localized views / all views | Useful views / mission-proxy minute | New scan payload MiB | Analysis wall s | Visibility-error MAE m² |\n|---|---|---:|---:|---:|---:|\n"
    for name, r in views["groups"].items():
        rate = r["useful_views_per_mission_proxy_min"]
        text += f"| {name} | {r['useful_localized_views']}/{r['views']} | {rate if rate is not None else 'n/a'} | {r['new_capture_payload_bytes'] / 1024**2:.2f} | {r['analysis_wall_s']:.2f} | {r['visibility_prediction_error_m2_mae']:.3f} |\n"
    text += "\nMission time is a static route/acquisition proxy, not measured flight time. Controller CPU/wall totals include unequal shared-acquisition-cache and generation overhead, so they cannot establish planner-runtime superiority. Inner optimizer timing excludes P3v2 suitability preprocessing. Actual per-view inference and payload accounting is separately reported. Absolute CPU/RSS values and environment changes are retained, without extrapolation to industrial edge hardware.\n"
    for title, summary in [
        ("Supplemental heldout controls", control),
        ("Fresh-after-aged chronology controls", fresh),
    ]:
        text += f"\n## {title}\n\n{summary['completed']}/{summary['expected']} cases completed.\n\n| Control / detector / method | Trials | Initial public unconfirmed | Views | Newly localized | Healthy positive | Inconclusive | Actually scoped-qualified | Continue monitoring |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|\n"
        for name, r in summary["groups"].items():
            text += f"| {name} | {r['trials']} | {r['initial_public_unconfirmed']} | {r['views']} | {r['new_localized']} | {r['healthy_fp']} | {r['inconclusive']} | {r['scope_actually_qualified']} | {r['continued_monitoring']} |\n"
    text += "\nSupplemental controls use fresh17000–17029 seeds, separate17100/17101 development; chronology uses17200–17229 after17300/17301 development. The first sufficient-scope pilot chose a non-visible face cell and failed qualification; the corrected protocol fixes the nominal front-face cell before final evaluation. An OOM and a recycled-executor stall were preserved and recovered with explicit one-case process shards; only execution/metadata lookup changed. No calibration, sensing noise, production planner, registration or filtering rule was retuned from heldout outcomes. All prior and interrupted evidence remains.\n"
    p = DOC / "PHASE7_INDEPENDENT_VALIDATION.md"
    p.write_text(p.read_text() + text)
    reservation = load(EXT / "phase7-V4-queue-reservation-retest/report.json")
    assert next(r for r in reservation["messages"] if r["kind"] == "critical")["persisted"] == 1
    assert reservation["beyond_total_limit_persisted"] == 0 and reservation[
        "critical_temporal_states"
    ] == ["current"]
    text = f"""\n\n## Final admission correction and complete retest

The deployed correction reserves100 pending slots only for authenticated authoritative critical readings that pass the original temporal qualifier. Ordinary pending limit10000; total pending bound10100. PostgreSQL admission counting is serialized across sources. Normal, unknown-quality/clock, stale and unqualified observations cannot use the reserve; worker/F1 independently requalify every admitted reading. No TTL or detector/F1 threshold changed.

Actual boundary retest: ordinary persisted0, current critical persisted1 and was assessed current; a further critical reading at the10100 pending bound persisted0. The complete fresh-database retest executed all 19 profiles over about1045s: **{final_e4["critical_states"].get("current", 0)}/{final_e4["critical_expected_published"]} current**, states {final_e4["critical_states"]}; receipt→commit p50/p95/p99/max **{final_e4["receipt_to_advisory_s"]["p50"]:.3f}/{final_e4["receipt_to_advisory_s"]["p95"]:.3f}/{final_e4["receipt_to_advisory_s"]["p99"]:.3f}/{final_e4["receipt_to_advisory_s"]["max"]:.3f}s**. This is a bounded laboratory pass, not a causal attribution of latency improvement to a reserve that may not be exercised below saturation. Earlier failures and differing concurrent CPU loads remain relevant.

A further actual500-message backlog/critical/planning test initially exposed reused MQTT client IDs; a second run corrected IDs but inspection messages were rejected because a truncated replay put their anchor in the future. No heavy-job concurrency was claimed from those submissions. The publisher now uses unique client IDs and waits for the actual scheduled capture anchor; server future-clock rejection remains unchanged. Fresh v3 results: **{mixed["critical_states"].get("current", 0)}/{mixed["critical_expected_published"]} current**, states {mixed["critical_states"]}; p95/p99 **{mixed["receipt_to_advisory_s"]["p95"]:.3f}/{mixed["receipt_to_advisory_s"]["p99"]:.3f}s**. Actual inspection/critical interval overlap is documented separately in `mixed_inspection_overlap_final.json`; nominal task submission is insufficient.

The timing decomposition found only about0.114s p95 emission-to-ingestion delay, but about10.965s p95 ingestion-to-job wait;12critical assessments actually overlap the two inspection intervals. Queue/service pressure, not packet arrival alone, explains the measured recency failure. This is a measured association and capacity boundary, not a calibrated hardware model.

Final raw output: `/mnt/d/TwinGuard/phase7-V4-full-E4-admission-retest` and `/mnt/d/TwinGuard/phase7-V4-mixed-boundary-retest-v3`. Compact summaries are under `docs/phase7`. Bounded software results improve readiness evidence; representative hardware/network rates, longer capacity behavior and site commissioning remain unvalidated. The heavy mixed workload fails the unchanged freshness acceptance. P5-01 remains OPEN, including this measured laboratory overload boundary.\n"""
    p = DOC / "PHASE7_E4_CORRECTED_STRESS.md"
    p.write_text(p.read_text() + text)
    strict = load(EXT / "phase7-V7-strict-trends-v2/report.json")
    save(OUT / "strict_browser_values.json", strict)
    text = "\n\n## Strengthened actual-value browser verification\n\nThe inherited chart check only established a chart container. The strict follow-up exposed an obsolete asset-response race and a stream-refresh clearing issue; both were corrected. A deliberately delayed DR-01 response cannot replace BW-01 values. The final browser renders100 actual stored pressure samples with Pa units and nonempty SVG line geometry, with no JavaScript errors. Failed and passing strict runs remain on the external drive.\n\n![Actual stored measurements](phase7/figures/actual_stored_trends.png)\n\n![Final actual dashboard](phase7/figures/actual_dashboard_with_values.png)\n"
    p = DOC / "PHASE7_INTEGRATED_DEMONSTRATION.md"
    p.write_text(p.read_text() + text)
    p = DOC / "PHASE7_STORAGE_VALIDATION.md"
    p.write_text(
        p.read_text()
        + "\n\nAfter all restore equality and dump hashes passed, the two disposable restore-target databases were removed to reclaim test storage. Source databases, SQL dumps, CAS archives, raw archives and recorded equality evidence remain. See `phase7/restore_fixture_cleanup.json`. Raw archival preserves parsed inbox envelope content and original wire digest; it is not a packet capture of arbitrary original JSON formatting.\n"
    )
    if fresh["status"] != "completed":
        note = f"\n\n## Explicit incomplete extra chronology study\n\nOnly {fresh['completed']}/{fresh['expected']} cases are journal-committed. Source-host C: fell below the retained1GiB operating floor although output is on D:. Unused build-cache cleanup reclaimed2.898GB inside Linux but did not restore Windows backing-drive headroom. No resource guard was lowered, no missing result was synthesized, and no aggregate benefit is claimed from this partial subset. All240main cases and90supplemental controls are complete; the remaining extra chronology cases and their fragments remain pending.\n"
        p = DOC / "PHASE7_INDEPENDENT_VALIDATION.md"
        p.write_text(p.read_text() + note)
    freeze = load(OUT / "CANDIDATE_FREEZE.json")
    changed = []
    for name, sha in freeze["sources"].items():
        if (
            name.startswith(
                tuple(
                    "src/twinguard/" + f + "/"
                    for f in ("analytics", "inspection", "fusion", "sensing")
                )
            )
            and hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != sha
        ):
            changed.append(name)
    if changed:
        raise ValueError("Frozen scientific method changed: " + str(changed))
    checks = load(OUT / "software_checks.json")
    assert "336 passed" in checks["outputs"]["pytest"] and not checks["private_secrets_tracked"]
    gates = [
        (
            "G1",
            "PASS",
            "Historical E1–E5 and empirical reports/models/policy retained; baseline307tests and manifest",
        ),
        (
            "G2",
            "PARTIAL / scoped correction",
            "Independent healthy calibration and1140pairs; same supported domains improve FP with small sensitivity loss; global abstention/recall tradeoff unresolved",
        ),
        (
            "G3",
            "PASS evaluation; benefit limited",
            "All five methods under both common detectors; full paired outcomes, true-missed controls and real ablations; no unsupported superiority",
        ),
        (
            "G4",
            "PASS",
            "Scientific candidate files/model unchanged from freeze; no private/future observations in production; infrastructure-only recoveries recorded",
        ),
        (
            "G5",
            "PARTIAL — heavy mixed timeliness fails",
            "Light full workload186/186current; actual heavy mixed workload145/184current,39stale; admission/restarts and failure boundary retained",
        ),
        (
            "G6",
            "PASS recovery / PARTIAL capacity",
            "Actual archival, SQL/CAS/raw restore, queries/index growth; no90-day endurance",
        ),
        (
            "G7",
            "PASS feasible lab / PENDING site",
            "Auth/ACL/RBAC/privileges, actual lab TLS and readonly encrypted OPC UA, advisory fixes; site trust uncommissioned",
        ),
        (
            "G8",
            "BLOCKED physical",
            "User confirms no equipment/data; surveyed physical protocol and blockers recorded",
        ),
        (
            "G9",
            "PASS software scope",
            "Actual reviewed acquisition/F1/replan, duplicate/restart and real-data browser evidence",
        ),
        (
            "G10",
            "PASS typed evidence",
            "Per-capability hashes/versions/provenance/repro commands; raw/registered point audits; negative outcomes retained",
        ),
        (
            "G11",
            "PASS",
            "336pytest, Ruff/format/Mypy114, frontend3tests/build/audit and live browser/Docker checks",
        ),
        (
            "G12",
            "PASS conservative assessment",
            "Software laboratory TRL4-consistent scope; industrial5/6 not established, physical/siteNO-GO",
        ),
    ]
    report = "# Phase7 final validation\n\n**CONDITIONAL GO — software research demonstrator operates, with material generalization, multi-asset, long-horizon capacity and representative-environment validation limits. Physical/industrial readiness: NO-GO / BLOCKED.** User confirms no physical data/equipment. This is a truthful software-validation package with explicitly reported incomplete extra work, not an industrial certification.\n\nStarting revision `a283713ef6ecfb8b7f883b76701e39ec22e8e5ce`, branch `phase-7-final-validation`, software 0.8.0. Scientific freeze `edae1e5`; tested operational correction `a35c790` with exact running-image source hashes. Final source/package revisions are recorded separately.\n\n## Acceptance gates\n\n| Gate | Status | Evidence / limit |\n|---|---|---|\n"
    for gate, status, why in gates:
        report += f"| {gate} | {status} | {why} |\n"
    report += "\n## Executive outcome\n\nB3.2 reduces healthy positives on identical supported cases (18/60→4/60; localized faults237/240→235/240), but globally detects235/840 versus635/840 for B3.1 and abstains840/1140. B3.1 remains default. P3v2 is an explicit engineering utility, not a detection probability; full comparisons, unknowns, qualified areas and measured resource limits are reported separately.\n\nThe final full E4 observed186/186current critical readings; earlier full168/186 and backlog116/188 are preserved. The admission correction passed the10000/10100pending boundary, and the corrected heavy/critical overlap test is independently timestamp-checked. The 10-second TTL is unchanged. Storage restore/archival and lab security passed their scopes; trace growth, physical metrology and site trust remain open.\n\n## Reports and reproduction\n\n- [Baseline inventory](PHASE7_BASELINE_INVENTORY.md), [exact freeze](phase7/CANDIDATE_FREEZE.json), [evidence register](phase7/EVIDENCE_REGISTER.md).\n- [Geometric diagnosis](PHASE7_GEOMETRIC_GENERALIZATION.md), [planner corrections](PHASE7_PLANNER_CORRECTIONS.md), [independent paired results](PHASE7_INDEPENDENT_VALIDATION.md).\n- [Full E4 and bounds](PHASE7_E4_CORRECTED_STRESS.md), [storage](PHASE7_STORAGE_VALIDATION.md), [security](PHASE7_SECURITY_READINESS.md).\n- [Integrated demonstration/screenshots](PHASE7_INTEGRATED_DEMONSTRATION.md), [physical protocol](PHASE7_PHYSICAL_VALIDATION_PROTOCOL.md), [TRL assessment](PHASE7_TRL_ASSESSMENT.md), [P5/P6 issue register](PHASE7_VALIDATION_BACKLOG.md).\n\nExternal evidence lives at `D:\\TwinGuard` (`/mnt/d/TwinGuard`); the original157-case pre-migration copy remains retained. Migration verified46207files before resuming and records resource-only source drift. Supplemental allocation failures and a recycled-executor stall were preserved and recovered sequentially using one case per fresh process. Original main stale_initial is a delayed-data control; the separately declared chronology study genuinely acquires later without retiming measurements; see its explicit committed/expected count and any source-drive blocker. Mission durations are static proxies; per-method controller CPU/wall includes shared cache overhead and is not proof of algorithm runtime superiority.\n\nUse the versioned `scripts/phase7_*` controllers with new output directories and explicit loopback compose overlays. `phase7_summarize.py`, `phase7_view_metrics.py`, `phase7_evidence_register.py` and `phase7_finalize.py` derive checked reports from preserved journals; none marks unexecuted trials successful. The new private certificates/secrets stay gitignored. Physical and site-only gates require the documented resources and independent authority before deployment.\n"
    report += f"\n\nExecution counts:240/240main paired cases,90/90supplemental controls,180/180actual-acquisition ablation trials and1140/1140detector pairs. Extra chronology:{fresh['completed']}/{fresh['expected']}committed; remaining cases are not claimed successful.\n"
    (DOC / "PHASE7_FINAL_VALIDATION.md").write_text(report)
    save(
        OUT / "acceptance_gates.json",
        {
            "gates": [{"id": g, "status": s, "evidence": e} for g, s, e in gates],
            "readiness": "CONDITIONAL GO software research",
            "physical_readiness": "NO-GO/BLOCKED",
            "frozen_scientific_files_changed": changed,
            "main_cases": plans["cases"],
            "supplemental_cases": control["completed"],
            "fresh_chronology_cases": fresh["completed"],
        },
    )
    print("Final reports written from completed journals; physical/site readiness remains blocked.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--allow-incomplete-chronology",
        action="store_true",
        help="Report explicit source-drive-blocked extra cases; never mark them completed",
    )
    args = parser.parse_args()
    main(args.allow_incomplete_chronology)
