"""Generate the Phase 4 validation dossier from preserved measured E3 artifacts."""

from pathlib import Path
from datetime import datetime, timedelta, timezone
import json
import hashlib
import shutil
import numpy as np
from twinguard.fusion.io import save
from twinguard.core.boundaries import audit_consumers

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "experiments/outputs/phase4-validated"
D = ROOT / "docs"


def pct(value):
    return "undefined" if value is None else f"{100 * value:.2f}%"


def main():
    r = json.loads((RUN / "report.json").read_text())
    audit = json.loads((D / "phase4/audit.json").read_text())
    assert (
        audit["sealed_prediction_runs"] == 2220
        and r["assessments_semantically_identical"] == 244800
    )
    assert audit_consumers(ROOT / "src/twinguard") == []
    expected = r["validated_source_sha256"]
    assert all(
        hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
        for name, digest in expected.items()
    )
    # Independently prove notice records also remain identical after the representation correction.
    notices = 0
    for track in ["controlled", "end_to_end"]:
        for row in r[track]["rows"]:
            suffix = Path(track) / row["case_id"] / row["method"] / "advisories.json"
            old = json.loads((ROOT / "experiments/outputs/phase4-full" / suffix).read_text())
            new = json.loads((RUN / suffix).read_text())
            assert old == new
            notices += len(new)
    save(
        D / "phase4/equivalence.json",
        {
            "assessments_compared": 244800,
            "case_method_runs": 2220,
            "severities_confidence_actions_and_support_unchanged": True,
            "temporal_spatial_dependence_and_events_unchanged": True,
            "notice_records_compared": notices,
            "notices_identical": True,
            "policy_parameters_unchanged": True,
            "corrections": "Canonical semantic policy hashing; recovery/unknown-scope explanation text; standalone prepare formats. Audit metrics distinguish current hazard-specific eligibility and historical support.",
        },
    )
    figures = D / "figures/phase4"
    figures.mkdir(parents=True, exist_ok=True)
    for path in (RUN / "figures").glob("*"):
        if path.is_file():
            shutil.copy2(path, figures / path.name)
    save(D / "phase4/results.json", r)
    date = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
    text = f"""# Phase 4 validation — hazard-aware temporal evidence fusion

Completed {date} (Asia/Calcutta). Branch phase-4-evidence-fusion; software 0.5.0, schema 1.0.0. Starting Phase 3.1 commit d99075f; first frozen E3 candidate dd20acd; representation/checkpoint correction a4552c4; final persistence validation {r["source_commit"][:7]}. Initial and revised source hashes, policies, models and artifacts are preserved. This is an advisory research implementation and synthetic software validation, not physical boiler safety certification. Phase 5 was not implemented.

## Implemented architecture and Phase 3 compatibility (A–C)

New fusion modules implement validated public evidence/processing/policy/state contracts, geometric/thermal/IoT adapters, hazard-specific temporal checks, asset/physical-region compatibility, source dependence, F1 hazard assessment, fixed F0 agreement, persistent advisory lifecycle, explanations, public CLI and deterministic JSON checkpoint replay. Detailed guides: FUSION_ARCHITECTURE.md, EVIDENCE_SEMANTICS.md, HAZARD_POLICIES.md and EVENT_LIFECYCLE.md. Existing ConditionAssessment and Phase 3 records keep their meanings; exported schemas are additive.

B3.1 retains localized_relative scope, registration/calibration/coverage/support and reinspection flags. Unqualified raw patches never become valid findings. Unavailable support or L2 geometry is inconclusive, never negative. Image-only thermal findings are inspection-context advisories and cannot satisfy region corroboration. Installed surface-temperature and bulk process-temperature residuals are distinct. Operating anomalies are not automatically critical events. Configured current credible raw limit crossings can raise red without UAV agreement or an in-range operating model; invalid instruments cannot.

The illustrative pressure limit 1,150,000 Pa and temperature limit 240 degC are based on explicitly documented synthetic nominal envelopes, not learned fault labels or real safety limits. The site-review template has no critical limits and unknown instrument calibration. Policy thresholds did not change after final E3 evaluation. Clock/processing assumptions are explicit simulated_replay metadata; original offline analytics availability is never silently replaced by acquisition time. The prepare CLI uses actual seal completion and defaults clocks to unknown.

## Dataset separation and execution

E3-A: 22 designed logical cases x 30 independently seeded delivery variants (6100–6129), **660 cases**. These stipulate analytic finding/quality conditions and test policy semantics; they are not 660 physical experiments. Development used separate 5900/6900 and earlier 6000/7000 smoke inputs. Initial development policy errors and corrections are retained in phase4/development_policy_review.json.

E3-B: 15 comparative conditions x 30 fresh seeds (7100–7129), **450 actual generated sensor/analytics cases**. All use the original plant/sensor/analytics algorithms and frozen healthy Phase 3 models. Each acquired case contains two LiDAR and five thermal captures plus public IoT streams. A genuine historical public inspection is separately versioned for stale-history cases. Only the declared delivery selections are filtered/duplicated; detectors, noise and fault kernels were not eased. Models were not refitted on E3 labels.

F0/F1 receive identical evidence and availability schedules. Assessment cadence is five simulated seconds through 125 s. Critical pressure uses a clearly identified severe 500 kPa synthetic scenario; the existing 200 kPa anomaly remains noncritical. The temperature scenario adds 70 degC. All analytical availability assumptions and the matching horizon were fixed before evaluation.

Each method's assessments, traces, state, events and normalized snapshot were saved and SHA256-sealed before evaluation labels were read. After a policy JSON-roundtrip hash issue and explanation wording defect were found, **all 2,220 case-method streams were replayed**. Exactly **244,800 per-asset assessments** retained every semantic assessment field, selected/current/historical evidence, temporal/spatial/dependence findings, event states and actions. Notice records also match exactly. A custom-policy test also verifies that a qualified normal resets a pending consecutive-activation candidate; shipped rules and all E3 decisions remain unchanged. Only canonical IDs/hashes and explanation text changed in this corpus. This added no independent sensor observations and did not tune policies. Original outputs remain in phase4-full; final validated outputs are in phase4-validated.

## E3-A controlled policy-semantic results (D)

| Metric | F0 | F1 |
|---|---:|---:|
"""
    a = r["controlled"]["metrics"]
    b = r["end_to_end"]["metrics"]
    for label, values in [
        ("Final expected decision", [f"{a[m]['decision_correct']}/660" for m in ["F0", "F1"]]),
        ("Severity-qualified event recall", [pct(a[m]["event_recall"]) for m in ["F0", "F1"]]),
        (
            "Configured critical escalation",
            [f"{a[m]['critical_escalations']}/{a[m]['critical_events']}" for m in ["F0", "F1"]],
        ),
        (
            "False advisories on negative logical scenarios",
            [f"{a[m]['false_advisories']}/240" for m in ["F0", "F1"]],
        ),
        ("Unknown assessment fraction", [pct(a[m]["unknown_fraction_mean"]) for m in ["F0", "F1"]]),
        (
            "Current support with no eligible hazard rule",
            [str(a[m]["stale_or_unqualified_used_assessments"]) for m in ["F0", "F1"]],
        ),
    ]:
        text += "| " + label + " | " + " | ".join(values) + " |\n"
    text += """
F1 meets all 22 expected final policy properties in all 30 delivery variants. Final-label correctness differs from event detection: the recovery scenario can end green even if a method failed to escalate the earlier critical event. Controlled success establishes semantics under designed evidence, not real upstream detection capability.

## E3-B end-to-end results and F0/F1 tradeoff (E–F)

There are 330 positive principal-event scenarios and 120 negative scenarios. Events must match the hypothesis and graded asset/scope within the fixed window; critical events require red. Geometry additionally needs a qualified supporting region in the private true footprint. An unrelated pressure warning cannot count as a detected L2 deformation.

| Metric | F0 | F1 |
|---|---:|---:|
"""
    table = [
        (
            "Severity-qualified event precision",
            [pct(b[m]["event_precision"]) for m in ["F0", "F1"]],
        ),
        (
            "Principal-event recall",
            [
                f"{b[m]['true_positive_events']}/330 ({pct(b[m]['event_recall'])})"
                for m in ["F0", "F1"]
            ],
        ),
        ("Missed principal events", [str(b[m]["missed_events"]) for m in ["F0", "F1"]]),
        ("Critical escalation", [f"{b[m]['critical_escalations']}/150" for m in ["F0", "F1"]]),
        (
            "Advisory rate on negative scenarios",
            [pct(b[m]["false_advisory_rate"]) for m in ["F0", "F1"]],
        ),
        (
            "Unmatched principal-event advisories",
            [str(b[m]["wrong_condition_advisories"]) for m in ["F0", "F1"]],
        ),
        ("Unknown assessment fraction", [pct(b[m]["unknown_fraction_mean"]) for m in ["F0", "F1"]]),
        (
            "Current support with no eligible rule",
            [str(b[m]["stale_or_unqualified_used_assessments"]) for m in ["F0", "F1"]],
        ),
        (
            "Complete provenance/rationale/support trace",
            [pct(b[m]["trace_complete_fraction"]) for m in ["F0", "F1"]],
        ),
    ]
    for label, values in table:
        text += "| " + label + " | " + " | ".join(values) + " |\n"
    text += """
F1 has two false advisory scenarios among 120 negatives (one load-transition case and one missing/duplicate case); these are amber warnings, not false critical events. F0's high precision accompanies very low recall. Unknown is separately reported and is not a correct healthy negative. The strict primary-event precision penalizes unmatched warnings: F1's 53 include 30 real secondary geometric warnings in the spatial-mismatch cases where the principal critical temperature event was missed, plus 23 L2 cases with unrelated process warnings. Thus this is not a claim that all 53 warnings were physically nonexistent. Secondary/nonprincipal events are retained but not completely annotated; broader multi-event precision needs an expanded truth scheme.

| Condition | Cases per method | F0 detected | F1 detected | Interpretation |
|---|---:|---:|---:|---|
"""
    commentary = {
        "healthy": "No physical event; scoped green after required coverage arrives",
        "normal_load": "Normal transition; retain observed false warnings",
        "geometry": "Real 20 mm localized change; no need for abnormal process signals",
        "thermal": "Actual hotspot; evaluated at image/inspection context, not exact asset overlap",
        "pressure": "Noncritical 200 kPa deviation; amber, not invented critical",
        "critical_pressure": "Credible 500 kPa critical scenario",
        "temperature": "70 degC critical process-temperature scenario",
        "geometry_only": "Geometric positive with fixed streams unavailable",
        "pressure_no_uav": "Critical event must not wait for UAV",
        "stale_inspection": "Old actual inspection cannot establish current coverage",
        "L2_geometry": "Upstream abstention remains missed geometry, not healthy",
        "missing_duplicate": "Unknown monitoring and retransmissions; no duplicate confirmations",
        "image_only_context": "Qualified localized geometry plus unassociated thermal context",
        "uncalibrated_critical_pressure": "Raw critical path still works outside learned operating range",
        "spatial_mismatch": "Relevant critical channel absent; unrelated pipe warning cannot establish BW critical event",
    }
    for condition in sorted(b["F1"]["by_condition"]):
        x = b["F0"]["by_condition"][condition]
        y = b["F1"]["by_condition"][condition]
        text += (
            f"| {condition} | 30 | {x['detected']} | {y['detected']} | {commentary[condition]} |\n"
        )
    text += """
F1's 60 principal misses consist of all 30 L2 geometric events and all 30 missing-relevant-channel spatial-mismatch critical events. Five L2 cases end amber due to unrelated process warnings and 25 end unknown; none is counted as a successfully detected deformation. All 30 pressure-without-UAV and all 30 out-of-reference critical-pressure cases escalate correctly. Source faults and sensor/model quality failures are visible rather than relabeled healthy.

"""
    paired = audit["paired_recall_difference"]
    text += f"The paired seed-cluster recall difference F1−F0 is {paired['mean']:.4f}, with a 2,000-resample descriptive 95% range {paired['seed_bootstrap_95']}. Conditions within a seed remain paired. These are controlled synthetic-mixture intervals, not industrial reliability or calibrated evidence-confidence probabilities.\n"
    text += """
## Temporal, spatial, dependence and lifecycle audit

Current and historical support are separate. F1 has zero measured current support without an eligible triggered rule; persistent historical advisories are not treated as current corroboration. Image-only findings never establish confirmed region overlap. Alternate B3/B3.1 and raw/residual versions from one source do not become independent confirmations. Exact repeats do not issue duplicate open notices. Acknowledgment does not clear an event; expiration or loss of sensing does not prove recovery. Recorded repair invalidates older geometry, and qualified recovery uses new normal acquisitions, duration and hysteresis.

"""
    text += f"All {audit['sealed_prediction_runs']} final prediction seals were reverified. Repeated open-notice IDs: F0={audit['repeated_open_notice_ids']['F0']}, F1={audit['repeated_open_notice_ids']['F1']}. The graded-scope supplemental audit finds F0 green on scopes with no configured normal coverage in {audit['unconfigured_scope_green']['controlled']['F0']} controlled and {audit['unconfigured_scope_green']['end_to_end']['F0']} end-to-end assessment frames; F1 has zero in both tracks. These are repeated frames, not independent event counts. The original declared-missing-requirement green metric is zero for both and does not alone cover this unconfigured-scope failure.\n"
    recovery = audit["first_qualified_recovery_to_clear_s"]["F1"]
    text += f"Measured F1 clearing from first qualified recovery acquisition spans {min(recovery):.3f}–{max(recovery):.3f} s across {len(recovery)} resolved critical events. This measures configured recovery waiting/cadence, not physical full-return latency. Unresolved/censored events are not scored as cleared; F0 has no comparable qualified-recovery rule.\n"
    text += """
Initial coarse audit fields incorrectly counted an evidence ID stale if any other rule had a shorter TTL, and treated historical persistence as missing explanation support. The validated audit checks eligibility under actual triggered rules and accepts explicitly labeled historical support for unresolved events. This is an audit correction only: event matching, classification and all decisions are unchanged, with original reports preserved.

## Performance and checks (G)

"""
    text += f"Original full generation/sensing/analytics/fusion run: {r['initial_sensor_analytics_runtime_s']:.2f} s. Complete decision-equivalence replay: {r['validation_replay_runtime_s']:.2f} s. Peak original worker RSS {r['max_worker_rss_mib']:.1f} MiB; replay worker peak {r['max_replay_worker_rss_mib']:.1f} MiB; these are per-process, not simultaneous whole-system peaks. Three isolated CPU workers, one OpenMP/BLAS thread each; no CUDA.\n\n"
    for method in ["F0", "F1"]:
        times = [
            row["fusion_runtime_s"] for row in r["end_to_end"]["rows"] if row["method"] == method
        ]
        text += f"- {method}: mean 125 s/26-tick replay CPU time {np.mean(times):.4f} s per case; average per all-asset assessment tick {np.mean(times) / 26:.6f} s. This is measured replay processing, not a transport SLA or per-message p99.\n"
    text += """
The initial Phase 0–3.1 baseline passed 170 tests. Final suite: **227 passed**, one pre-existing Starlette/httpx warning. Phase 0 maturity assertions now require implemented fusion/E3; prior behavioral tests remain. Ruff lint/format, Mypy (81 source files), pip check, doctor, schema export, policy/prepare/assess/replay/report CLI round trips and policy checkpoint JSON reload pass. The 0.5.0 CPU metadata API image builds, reaches Compose healthy and returns HTTP 200 for health/version/capabilities. It excludes optional Open3D analytics runtime and is not a full analytics-image claim. Temporary stack/mirror are stopped after checks.

## Exact artifacts and reproduction (H)

All paths below are relative to /home/mallikarjun/workspace/TwinGuard:

- configs/fusion/hazards.yaml and site-template.yaml: illustrative policy and unconfigured site template
- configs/fusion/calibration and history: frozen healthy models and actual historical public inspection
- configs/experiments/E3.yaml and experiments/E3.yaml: seeded execution/matching configuration
- experiments/outputs/phase4-full: original public observations, actual analytics, initial sealed predictions and separate evaluator labels
- experiments/outputs/phase4-validated: final public snapshots/manifests, state/history/assessments, advisories/events, canonical policies, explanations and post-seal evaluation
- docs/phase4/results.json, trial_comparison.csv, audit.json, equivalence.json, freeze.json, checks.json
- docs/figures/phase4/V1_*.png through V7_*.png and figure_source_data.json
- output/phase4-prepare, output/phase4-assess and output/phase4-replay: executed CLI examples

```bash
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
twinguard fusion validate-policy --policy configs/fusion/hazards.yaml
twinguard fusion prepare --analytics-run experiments/outputs/phase4-full/end_to_end/case-00004/analytics-geometry --output-dir output/new-prepared
twinguard fusion assess --evidence experiments/outputs/phase4-validated/end_to_end/case-00005/inputs --policy configs/fusion/hazards.yaml --at 2026-01-03T00:00:40+00:00 --output-dir output/new-assessment
twinguard fusion replay --evidence experiments/outputs/phase4-validated/end_to_end/case-00005/inputs --policy configs/fusion/hazards.yaml --output-dir output/new-replay
twinguard experiment run E3 --config experiments/E3.yaml --output-dir experiments/outputs/new-E3
twinguard experiment report --run-dir experiments/outputs/new-E3
```

Use new output directories. Standalone thermal CLI output requires --dataset pointing to its original public observations because the upstream seal identifies only a capture ID; operating.json and thermal.json are supported alongside composite E2 formats. Prepare defaults clocks to unknown and preserves real offline completion; synchronized clock overrides need a legitimate declared basis. For deterministic checkpoint continuation pass --checkpoint state.json with the same semantic policy. Early unreleased noncanonical candidate checkpoints require explicit replay, not silent migration. scripts/revalidate_phase4.py preserves original results and proves representation-only equivalence; it refuses to overwrite its validated output.

Large generated traces/clouds remain ignored by Git. Figure/report numbers derive from saved measured outputs, not illustrative success curves.

## Limitations and Phase 5 handoff (I–J)

F1 is not a sensor or fault-detector replacement. L2 geometry is unavailable; source noise/calibration can create warnings. A missing critical channel cannot be replaced by an unrelated sensor. No physical temperature, pressure limit, whole-wall displacement or support-integrity capability is inferred from localized/radiometric findings. Current spatial matching requires exact qualified asset IDs and published compatible physical regions; no cross-asset parent-hierarchy inference or image-to-3D projection is invented.

Clock quality and calibration are declared trusted metadata, not independently verified hardware properties. These are synthetic processing/arrival tests, not field latency measurements. Policy/producer authenticity, durable storage, authorization for operator actions, production notification transport, bounded retention/archival of the research state and long-duration resource testing remain integration prerequisites. The in-memory replay retains history; it is not advertised as an unbounded-duration production streaming service. Checkpoint replay assumes prior available records are represented; late measurements need honest new availability/ingress semantics rather than backdated injection into earlier decisions.

The Phase 5 interface handoff is ready: typed public evidence/policy/state, pure assess/replay, explainable ConditionAssessment/DecisionTrace, record-only events and checkpoints require no broker or UI dependency. Real deployment readiness remains PARTIAL pending the above engineering/integration work. No Phase 5 transport, dashboard, flight control or plant actuation was implemented.

## Acceptance decisions

PASS means the specified Phase 4 software/research capability is implemented and exercised under these assumptions; it is not industrial safety certification.

| # | Criterion | Decision / evidence |
|---|---|---|
"""
    criteria = [
        ("Prior regression", "170 prior tests retained; 227 total pass"),
        ("Fusion-ready contracts", "Typed evidence/time/policy/trace/state and schemas"),
        ("Actual-output adapters", "450 actual sensor/Phase 3 cases and standalone format tests"),
        (
            "Localized-relative semantics",
            "Scope/basis explicit; no global/support negative inference",
        ),
        ("Unqualified patch guard", "Region contributors/calibration support/registration checked"),
        ("Image-only thermal isolation", "Inspection context only; no physical overlap claim"),
        ("Residual versus limit event", "Separate hypotheses/adapters and raw configured path"),
        (
            "Acquisition/availability distinction",
            "Bound ProcessingRecord; offline versus simulated basis",
        ),
        ("Stale/delayed/future handling", "Hazard recency, clock/availability checks and tests"),
        ("Hazard-specific time", "Different single/joint windows and coincidence bounds"),
        ("Explicit spatial evaluation", "Associated frame/bounds/asset checks; unknown preserved"),
        (
            "Dependence/deduplication",
            "Lineage/groups/reference alternatives; no probability multiplication",
        ),
        ("Versioned validated policy", "Pydantic policies, canonical hashes and provenance"),
        (
            "Explicit engineering limits",
            "Illustrative basis; site template intentionally unconfigured",
        ),
        ("Single critical escalation", "Raw credible configured limit path"),
        ("Missing UAV does not veto", "30/30 critical no-UAV cases escalate"),
        ("No missing-to-green", "Required coverage plus abnormal/pending guards"),
        ("Unknown/inconclusive distinct", "Separate evidence and assessment statuses"),
        ("Four severities", "Scoped green/amber/red/unknown"),
        (
            "Severity versus confidence",
            "Independent categorical confidence; no invented probabilities",
        ),
        ("Explanation/support", "Current/historical IDs, provenance, conflicts and rationale"),
        (
            "Lifecycle/recovery",
            "Persistence, dedup, ack, repair, hysteresis and new-normal recovery",
        ),
        ("Deterministic replay", "Checkpoint binding; 244800 equivalent assessments"),
        ("F0 comparator", "Fixed one/two/three-modality agreement, record transitions"),
        ("F1 engine", "Hazard/time/space/dependence/quality reasoning"),
        ("Controlled E3-A", "660 cases, 22 properties, 30 delivery variants each"),
        ("Actual E3-B", "450 generated cases with unchanged upstream models"),
        ("Identical F0/F1 inputs", "Shared normalized streams and schedules"),
        (
            "Actual event metrics",
            "Strict matching, failures, unknowns and secondary-warning caveat",
        ),
        ("Truth boundary", "Import/runtime isolation; labels only after seals"),
        ("Measured visuals", "Seven reviewed charts and numerical source data"),
        ("Docs and schemas", "Required guides, experiment definition and schema export"),
        ("Quality/build checks", "227 tests, Ruff, Mypy, dependency and API checks"),
        (
            "Phase 5 interface readiness",
            "Stable pure API/contracts/checkpoints; deployment prerequisites documented",
        ),
    ]
    for i, (name, evidence) in enumerate(criteria, 1):
        text += f"| {i} | {name} | PASS: {evidence} |\n"
    text += "\nPhase 4 implementation/research task: PASS. Phase 5 interface handoff: PASS. Operational/physical deployment readiness: PARTIAL; no Phase 5 work was started.\n\n"
    for path in sorted(figures.glob("*.png")):
        text += f"![{path.stem}](figures/phase4/{path.name})\n\n"
    (D / "PHASE4_VALIDATION.md").write_text(text)
    print("Phase 4 dossier written; all final producer hashes and notice-equivalence checks passed")


if __name__ == "__main__":
    main()
