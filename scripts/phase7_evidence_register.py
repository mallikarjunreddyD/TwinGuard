"""Evidence-type-specific capability register. No missing result becomes a pass."""

from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/phase7"


def main():
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    items = []

    def add(
        ident,
        objective,
        path,
        test,
        acceptance,
        status,
        uncertainty,
        source="synthetic_software",
        baseline="a283713ef6ecfb8b7f883b76701e39ec22e8e5ce",
        command="",
        calibration="Original B3.1/thermal/operating models and F1 policy retained; optional separate view model where stated",
    ):
        p = Path(path)
        p = p if p.is_absolute() else ROOT / p
        available = p.is_file()
        items.append(
            {
                "capability_id": ident,
                "objective": objective,
                "software_version": "0.8.0",
                "source_git": commit,
                "scientific_candidate_git": "edae1e5",
                "data_reference": str(p),
                "data_source_type": source,
                "environment": "WSL CPU software; actual Docker protocols/database/browser where applicable; not physical/relevant-environment validation",
                "calibration_reference": calibration,
                "test": test,
                "acceptance_criterion": acceptance,
                "actual_result_status": status
                if available
                or source
                in (
                    "physical",
                    "external_independent_data",
                    "relevant_environment",
                    "commissioning",
                )
                else "INCOMPLETE missing artifact",
                "actual_artifact_sha256": hashlib.sha256(p.read_bytes()).hexdigest()
                if available
                else None,
                "baseline_reference": baseline,
                "uncertainty_and_limitations": uncertainty,
                "status": status,
                "reproduction_command": command,
                "artifact": str(p),
            }
        )

    add(
        "TG7-BASE",
        "Retain and reproduce historical baseline",
        "docs/phase7/baseline_manifest.json",
        "307 baseline tests; frozen original provenance",
        "Original records/models/policy retained",
        "PASS",
        "Software baseline reproduction, not scientific or physical revalidation",
        command="git show a283713ef6ecfb8b7f883b76701e39ec22e8e5ce; .venv/bin/python -m pytest -q",
    )
    add(
        "TG7-GEO-DIAG",
        "Diagnose view-dependent false positives",
        "docs/phase7/V1_E5_diagnostics.json",
        "30 retrospective healthy cases and 216 new matrix pairs",
        "Explain interactions without claiming unique cause",
        "PASS scoped diagnosis",
        "Retrospective associations; fresh matrix does not reproduce every historical FP",
        command=".venv/bin/python scripts/phase7_diagnose.py --help; .venv/bin/python scripts/phase7_view_matrix.py --help",
    )
    add(
        "TG7-CAL",
        "Independent healthy view calibration",
        "docs/phase7/V1_calibration_summary.json",
        "600 actual scan pairs, separate fit/screen seeds",
        "Qualified domains or explicit abstention",
        "PARTIAL 12 of 20 domains",
        "Only 10–15 valid independent screen scans/domain; no guaranteed 95% generalization bound",
        command=".venv/bin/python scripts/phase7_calibrate_views.py --help",
        calibration="configs/validation/view_calibration.json; independent fit14000..14014/screen14100..14114",
    )
    add(
        "TG7-DET",
        "Independent common-measurement detector comparison",
        "docs/phase7/heldout_detector_summary.json",
        "1140 new pairs / 30 final seed clusters",
        "Report recall, FP, abstention and uncertainty without promotion unless justified",
        "PASS evaluation; superiority NOT demonstrated",
        "B3.2 235/840 localized, 4/300 healthy positives, 840/1140 inconclusive; lower FP is accompanied by lost recall",
        command=".venv/bin/python scripts/phase7_detector_study.py --partition heldout --output <new> --workers 2",
    )
    planner = json.loads((DOC / "heldout_planner_summary.json").read_text())
    add(
        "TG7-PLAN",
        "Fair five-planner paired comparison under two common detectors",
        "docs/phase7/heldout_planner_summary.json",
        f"{planner['cases']}/{planner['expected_cases']} paired case journal entries",
        "Complete frozen seed-paired outcomes and retain negatives",
        "PASS evaluation" if planner["status"] == "completed" else "INCOMPLETE",
        "No whole-asset or calibrated fault-detection probability claim; identical observations share controller acquisition cache, so wall/CPU totals include unequal cache/generation overhead and do not establish planner-runtime superiority",
        command="TWINGUARD_CAMPAIGN_STORAGE=/mnt/d/TwinGuard .venv/bin/python scripts/phase7_planner_study.py --partition heldout --output experiments/outputs/phase7-V3-heldout-planners --workers 2 --resume",
    )
    add(
        "TG7-ABL",
        "Execute six real-acquisition component ablations",
        "docs/phase7/acquisition_ablation_summary.json",
        "180 new initial/reinspection trials",
        "Actually sense and rerun downstream processing, distinguish uninformative zero-view variants",
        "PARTIAL component interpretation",
        "Some removals select no further views; no component benefit can be inferred from an inactive ablation",
        command=".venv/bin/python scripts/phase7_planner_study.py --ablations --partition heldout --output <new> --workers 2",
    )
    add(
        "TG7-CONTROL",
        "Missed-view, independent-obstacle, measured scoped-coverage controls",
        "/mnt/d/TwinGuard/phase7-V3-supplemental-heldout-controls/campaign.json",
        "Separate protocol, fresh final17000..17029; development17100/17101",
        "Actual public unconfirmed state, independently modeled static obstacle shared with prior, and measured explicit scope",
        "PASS execution"
        if json.loads(
            Path(
                "/mnt/d/TwinGuard/phase7-V3-supplemental-heldout-controls/campaign.json"
            ).read_text()
        )["status"]
        == "completed"
        else "INCOMPLETE",
        "Tiny scoped geometry is not whole-asset health; equivalent multi-asset calibration remains absent",
        command="TWINGUARD_CAMPAIGN_STORAGE=/mnt/d/TwinGuard .venv/bin/python scripts/phase7_supplemental_controls.py --output <new>",
    )
    add(
        "TG7-E4",
        "Full corrected mixed-workload operational boundary",
        "docs/phase7/V4-full-E4-recovery-retest-summary.json",
        "19 profiles / 6204 completed jobs / 99 concurrent plans",
        "Report all critical freshness and recovery; no TTL changes",
        "PARTIAL critical acceptance failed",
        "168/186 current; 18 stale. Workstation contention, loopback timing, no hardware guarantee",
        command=".venv/bin/python scripts/phase7_e4_corrected.py --output <new>",
    )
    add(
        "TG7-BACKLOG",
        "Critical stream with measured ordinary backlog",
        "docs/phase7/V4-backlog-critical-summary.json",
        "500 measured paused ordinary messages then fresh critical streams",
        "Every published critical observation current",
        "FAIL timeliness",
        "116/188 current;72 stale; low receipt latency alone omits pre-ingestion delay",
        command=".venv/bin/python scripts/phase7_critical_boundary.py --output <new>",
    )
    add(
        "TG7-CAPACITY",
        "Expose saturated-admission loss",
        "docs/phase7/queue_saturation.json",
        "10000 fixture pending jobs, actual MQTT ordinary/critical publications",
        "Bounded rejection reported; critical loss not hidden",
        "FAIL original critical admission",
        "Fixture jobs are clearly labeled fault injection, not throughput observations",
        command=".venv/bin/python scripts/phase7_queue_boundary.py",
    )
    add(
        "TG7-RESERVE",
        "Correct bounded current-critical admission",
        "/mnt/d/TwinGuard/phase7-V4-queue-reservation-retest/report.json",
        "Actual MQTT at10000 and10100 jobs; current temporal qualification",
        "Ordinary rejects, current authoritative critical admitted, total bound enforced",
        "PASS boundary; full timing separately tested",
        "Not a transport-latency fix; no untrusted priority, stale/uncertain/normal observations cannot use reserve",
        command=".venv/bin/python scripts/phase7_queue_reservation_retest.py",
    )
    add(
        "TG7-E4-FINAL",
        "Full mixed workload after admission correction",
        "/mnt/d/TwinGuard/phase7-V4-full-E4-admission-retest/report.json",
        "Fresh isolated PostgreSQL/MQTT/API/worker/browser run",
        "Complete profiles and evaluate each published critical reading",
        "PASS bounded full execution; mixed overload separately fails"
        if Path("/mnt/d/TwinGuard/phase7-V4-full-E4-admission-retest/report.json").exists()
        else "INCOMPLETE",
        "Do not substitute the focused admission test for full-workload reliability",
        command=".venv/bin/python scripts/phase7_e4_admission_retest.py --output <new>",
    )
    add(
        "TG7-ARCHIVE",
        "Preserve history while externalizing raw payloads",
        "docs/phase7/archive_validation.json",
        "5120 completed inbox messages, actual recovery and duplicate replay",
        "No unresolved/scientific deletion; recover and verify digest",
        "PASS bounded archive",
        "SQL F1 trace growth remains; archive store must accompany backup",
        command=".venv/bin/python scripts/phase7_archive_validate.py",
    )
    add(
        "TG7-RESTORE",
        "Actual SQL/CAS/raw archive disaster recovery",
        "docs/phase7/archive_recovery.json",
        "Live exported snapshot pg_dump, new-db pg_restore, all table hashes,60 CAS files,5120 raw messages",
        "Every restored table/hash and referenced artifact matches",
        "PASS tested recovery",
        "Source lab workload and overnight idle history; no90-day endurance",
        command=".venv/bin/python scripts/phase7_storage_validate.py --output <new> --restore-name phase7_restore_<new> --archive-root <raw-store>",
    )
    add(
        "TG7-AUTH",
        "Source, clock, schema, RBAC and artifact rejection",
        "docs/phase7/security_checks.json",
        "Actual invalid MQTT/API/bundle requests",
        "Unauthorized requests rejected/quarantined",
        "PASS lab scope",
        "No site identities/enterpriseSSO/clock commissioning",
        command=".venv/bin/python scripts/phase7_security_checks.py --output <new-file>",
    )
    add(
        "TG7-TLS",
        "Actual lab TLS and read-only encrypted OPC UA",
        "docs/phase7/lab_tls.json",
        "Fresh lab CA, HTTPS/MQTT, pinned SignAndEncrypt, write/plaintext rejection",
        "Secure lab connection and rejection cases execute",
        "PASS lab scope",
        "Two-day selfsigned lab CA; first two failed attempts preserved; no approved site trust",
        command=".venv/bin/python scripts/phase7_lab_tls.py",
    )
    add(
        "TG7-DEPS",
        "Review and correct dependency findings",
        "docs/phase7/npm_audit_after.json",
        "OSV118Pythonpackages; npm before/after upgrade; tests/build",
        "Record findings and recheck correction",
        "PASS checked scopes",
        "No base-image/OS scan; time-limited advisory sources",
        command='.venv/bin/python scripts/phase7_dependency_review.py; docker run --rm -v "$PWD/frontend:/app:ro" -w /app node:22-slim npm audit --json --package-lock-only',
    )
    add(
        "TG7-DEMO",
        "Execute reviewed plan/acquire/F1/replan and real browser recovery",
        "docs/phase7/integrated_browser_recovery.json",
        "Actual backend and imperfect sensing, linked result, duplicate delivery/restart and12browserchecks",
        "Traceable working software chain; no duplicate opens",
        "PASS software scope",
        "Local test principal is not human/site approval; original negative detector outcomes retained",
        command=".venv/bin/python scripts/phase7_integrated_reinspection.py; .venv/bin/python scripts/phase7_integrated_capture.py",
    )
    add(
        "TG7-PHYSICAL",
        "Independent surveyed LiDAR/thermal measurement validation",
        "docs/PHASE7_PHYSICAL_VALIDATION_PROTOCOL.md",
        "Proposed surveyed10/20/30/50mm targets and thermal calibration",
        "Actual equipment, independent calibration and blinded results",
        "BLOCKED no equipment/data",
        "User explicitly confirms unavailable; no physical result fabricated",
        source="physical",
        command="Not executable until equipment, survey and approval prerequisites exist",
    )
    add(
        "TG7-EXTERNAL",
        "Independent external industrial data",
        "datasets/public/manifest.json",
        "Manifest provenance/license review",
        "Verified actual independent measurements and approved license",
        "PENDING no verified data",
        "Repository manifests are templates, not validation datasets",
        source="external_independent_data",
    )
    add(
        "TG7-RELEVANT",
        "Representative edge/site operating environment",
        "docs/PHASE7_PHYSICAL_VALIDATION_PROTOCOL.md",
        "Target hardware/network/process tests",
        "Independent relevant-environment performance",
        "PENDING",
        "Workstation/loopback does not demonstrate physical industrial equivalence",
        source="relevant_environment",
    )
    add(
        "TG7-COMMISSION",
        "Approved site trust, limits and instrument authority",
        "docs/PHASE7_SECURITY_READINESS.md",
        "Site certificate/identity/clock/calibration/limit signoff",
        "Attributable commissioned site evidence",
        "BLOCKED/PENDING",
        "Lab certificates and simulation limits do not commission a site",
        source="commissioning",
    )
    add(
        "TG7-MIXED",
        "Measure real inspection/critical overlap and failure boundary",
        "docs/phase7/mixed_inspection_overlap_final.json",
        "Two actual heavy inspection jobs overlap12critical assessments;145/184current,39stale",
        "All published critical readings remain current under declared load",
        "FAIL 10x heavy timeliness",
        "Queue-to-job p95 about10.965s dominates; no TTL relaxation or admission guarantee can revive stale samples",
        command=".venv/bin/python scripts/phase7_mixed_boundary_retest_v3.py --output <new>",
    )
    add(
        "TG7-TRENDS",
        "Render actual stored values and reject obsolete asset responses",
        "/mnt/d/TwinGuard/phase7-V7-strict-trends-v2/report.json",
        "100stored pressure samples, real SVG line, delayed obsolete asset response",
        "Stored values persist for current selection; no JavaScript errors",
        "PASS",
        "Earlier container-only and first strict failures retained",
        command=".venv/bin/python scripts/phase7_browser_trends.py",
    )
    add(
        "TG7-FRESH",
        "Acquire genuinely later scans after aged initial evidence",
        "/mnt/d/TwinGuard/phase7-V3-freshness-heldout/campaign.json",
        "Separate untouched17200..17229seeds after development17300/17301",
        "Original timestamps retained; every acquired new scan follows its frozen decision",
        "PASS execution"
        if json.loads(
            Path("/mnt/d/TwinGuard/phase7-V3-freshness-heldout/campaign.json").read_text()
        )["status"]
        == "completed"
        else "INCOMPLETE",
        "Main stale_initial is a late-delivery control; this separate protocol fixes chronology before final seeds",
        command="TWINGUARD_CAMPAIGN_STORAGE=/mnt/d/TwinGuard .venv/bin/python scripts/phase7_freshness_control.py --output <new>",
    )
    data = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_git": commit,
        "capabilities": items,
    }
    (DOC / "evidence_register.json").write_text(json.dumps(data, indent=2) + "\n")
    text = "# Phase7 evidence register\n\nDetailed per-capability objective, source/version/git, data type, calibration, test, criterion, actual artifact hash, baseline, uncertainty and reproduction command are in [evidence_register.json](evidence_register.json). The status distinguishes test execution from research benefit and physical readiness.\n\n| ID | Objective | Status | Evidence type |\n|---|---|---|---|\n"
    for item in items:
        text += f"| {item['capability_id']} | {item['objective']} | {item['actual_result_status']} | {item['data_source_type']} |\n"
    (DOC / "EVIDENCE_REGISTER.md").write_text(text)
    print(len(items), "capability records")


if __name__ == "__main__":
    main()
