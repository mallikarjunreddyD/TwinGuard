"""Write evidence-linked Phase7 operational reports from actual preserved measurements."""

from pathlib import Path
import json
from datetime import datetime
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs"
E = ROOT / "experiments/outputs"
T = DOC / "phase7"


def load(p):
    return json.loads(p.read_text())


def write(name, text):
    (DOC / name).write_text(text + "\n")


def copy_json(source, name):
    d = load(source)
    (T / name).write_text(json.dumps(d, indent=2) + "\n")
    return d


def main():
    full = load(T / "V4-full-E4-recovery-retest-summary.json")
    back = load(T / "V4-backlog-critical-summary.json")
    archive = copy_json(E / "phase7-V5-archive-validation/report.json", "archive_validation.json")
    recovery = copy_json(E / "phase7-V5-archive-recovery/report.json", "archive_recovery.json")
    first = copy_json(E / "phase7-V5-storage-recovery/report.json", "storage_recovery.json")
    copy_json(E / "phase7-V6-lab-tls-v3/report.json", "lab_tls.json")
    copy_json(E / "phase7-V6-security", "security_checks.json")
    copy_json(
        E / "phase7-V6-dependency-review/report.json", "python_advisory_review.json"
    )
    inspection = copy_json(
        Path("/mnt/d/TwinGuard/phase7-V7-reviewed-reinspection/report.json"),
        "integrated_reinspection.json",
    )
    browser = copy_json(
        Path("/mnt/d/TwinGuard/phase7-V7-browser-and-recovery/report.json"),
        "integrated_browser_recovery.json",
    )
    copy_json(E / "phase7-V4-queue-saturation/report.json", "queue_saturation.json")
    (T / "figures").mkdir(exist_ok=True)
    detector = load(T / "heldout_detector_summary.json")
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.5), layout="constrained")
    for ax, key, title in zip(
        axes,
        ["healthy_fpr", "localized_recall", "inconclusive"],
        ["Healthy positive scans", "Unconditional localized recall", "Inconclusive scans"],
    ):
        for i, m in enumerate(["B3.1", "B3.2"]):
            d = detector["methods"][m]["all"]
            if key == "inconclusive":
                v = d[key] / d["scans"]
                err = None
            else:
                v = d[key]["estimate"]
                lo, hi = d[key]["ci95"]
                err = np.array([[v - lo], [hi - v]])
            ax.bar(i, v, color=["#3975a5", "#d67832"][i], yerr=err, capsize=4)
        ax.set_xticks([0, 1], ["B3.1", "B3.2"])
        ax.set_ylim(0, 1)
        ax.set_title(title)
        ax.grid(axis="y", alpha=0.2)
        ax.set_axisbelow(True)
    fig.suptitle(
        "Phase 7: 1,140 heldout pairs / 30 seed clusters\nLower false positives accompany much greater abstention and lost recall",
        fontsize=11,
    )
    fig.savefig(T / "figures/detector_tradeoff.png", dpi=160)
    plt.close(fig)
    text = """# Phase 7 independent validation

Frozen production candidates: `edae1e5`, software 0.8.0. No detector, registration, sensing, calibration or utility tuning followed final evaluation. Source/model hashes and disjoint seed ranges are in `phase7/CANDIDATE_FREEZE.json`. The later destination-aware resource guard is an infrastructure change with separately retained provenance, not scientific tuning.

## Detector heldout results

All **1,140 actual scan pairs** completed: 900 L1 pairs, plus 240 L0/L2 stress pairs. Thirty independent final seeds (15000–15029), six L1 views, healthy and 10/20/30/50 mm targets, steady and load-transition cases. Same measured pair, same registration and original quality gates feed both detectors. Public predictions are sealed before footprint evaluation. Confidence intervals resample whole seeds, 2,000 replicates, fixed RNG; they describe this synthetic distribution, not physical generalization.

| Detector | Localized faults | Recall (95% seed-cluster CI) | Healthy positive scans | FPR (95% CI) | Inconclusive | Region precision |
|---|---:|---|---:|---|---:|---|
"""
    for m in ("B3.1", "B3.2"):
        d = detector["methods"][m]["all"]
        r = d["localized_recall"]
        f = d["healthy_fpr"]
        p = d["region_precision"]
        text += f"| {m} | {round(r['estimate'] * d['faults'])}/{d['faults']} | {r['estimate']:.3f} ({r['ci95'][0]:.3f}–{r['ci95'][1]:.3f}) | {round(f['estimate'] * d['healthy'])}/{d['healthy']} | {f['estimate']:.3f} ({f['ci95'][0]:.3f}–{f['ci95'][1]:.3f}) | {d['inconclusive']}/{d['scans']} | {p['estimate']:.3f} |\n"
    text += """
B3.2 is **not promoted**: its false-positive reduction is accompanied by much more abstention and substantially lower unconditional recall. Qualified-only comparisons select different subsets. Both have 189 registration failures; B3.2 calibration applies to only 300 scans. L2 remains unsupported. Per-fidelity, view, qualification and timing rows remain in the case journals; aggregate per-fidelity uncertainty is in `phase7/heldout_detector_summary.json`.

![Detector tradeoff](phase7/figures/detector_tradeoff.png)

## Paired planners and real acquisition ablations

The predeclared main campaign contains 240 cases × five planners × two common detectors. Initial/new/cumulative/additional/confirmation recall are separate, localization requires qualified significant patch-center overlap, and healthy positives/inconclusive/area/yield/actual CPU/RSS are retained. The source initial partial-view family unexpectedly detects all B3.1 targets; its label is not accepted as proof of a previously missed defect. A separately frozen supplemental protocol uses a fixed accepted-map left view, an independent static occluder shared with the accepted map, and an explicitly tiny measured sufficient-coverage scope. Development seeds 17100/17101 are separate from final controls 17000–17029.

All six acquisition ablations completed 180 fresh trials. Some variants select zero further views; those are **uninformative about reinspection benefit**, despite actually reacquiring their initial scan pairs. B3.2 selected-view totals across the six removals are 30 (adaptive replanning), 49 (calibration applicability), 58 (coverage history), 50 (redundancy penalty), 43 (registration suitability), and 26 (risk priority). Do not compare an incomplete main campaign subset against all 30 ablation seeds. Final main/supplemental results require completed journals; current status is recorded in the linked summaries, not inferred from software tests.

Artifacts: `phase7/heldout_planner_summary.json`, `phase7/acquisition_ablation_summary.json`, main case journal at `experiments/outputs/phase7-V3-heldout-planners`, and external controls at `/mnt/d/TwinGuard/phase7-V3-supplemental-heldout-controls`. Commands: `scripts/phase7_detector_study.py`, `scripts/phase7_planner_study.py`, `scripts/phase7_supplemental_controls.py`, and `scripts/phase7_summarize.py`. Use a new output directory; explicit resume verifies checkpoint hashes. External-drive migration retains the original evidence and records its allowed infrastructure-only source changes.
"""
    write("PHASE7_INDEPENDENT_VALIDATION.md", text)
    text = f"""# Phase 7 corrected full E4 stress

**Execution completed; critical timeliness acceptance FAILED. P5-01 remains OPEN.** Real CPU/Docker/PostgreSQL/MQTT/OPC UA/API/Chromium operation, not emulated transport latency or field hardware.

The first fresh full attempt (`phase7-V4-full-E4`) stopped at an actual queue-drain timeout after 872.4 s amid overlapping backlog streams. Its raw report and timestamp seal are retained. The fresh isolated retest (`phase7-V4-full-E4-recovery-retest`) used a declared 900 s bounded recovery observation window instead of the first controller's 240 s drain window. **No 10 s critical TTL, qualification gate or F1 rule changed.** This retest is not a latency fix or proof of critical reliability.

The retest executed **19 profiles over 1048.21 s**, including three normal streams, three pressure-critical streams before any UAV input, accelerated normal streaming, duplicates/reordering, worker/broker/API/database restart, real read-only numeric OPC UA, missing-data monitoring, LiDAR/thermal/L2 inspection and a live browser. **99 concurrent P3v2 requests** exercised the bounded planning worker. All **6204 jobs** ended completed. Per-profile completeness, API latency/statuses and samples are in the raw report and `phase7/V4-full-E4-recovery-retest-summary.json`. Transient API 502 responses occurred during intentional interruptions; do not describe uninterrupted availability.

| Critical workload | Actually published critical readings | Current | Stale | Missed among published denominator | Receipt→advisory p50 / p95 / p99 / max s |
|---|---:|---:|---:|---:|---|
| Full retest | {full["critical_expected_published"]} | {full["critical_states"].get("current", 0)} | {full["critical_states"].get("stale", 0)} | {full["critical_states"].get("missed", 0)} | {full["receipt_to_advisory_s"]["p50"]:.3f} / {full["receipt_to_advisory_s"]["p95"]:.3f} / {full["receipt_to_advisory_s"]["p99"]:.3f} / {full["receipt_to_advisory_s"]["max"]:.3f} |
| Measured 500-message paused ordinary backlog, overlapping streams | {back["critical_expected_published"]} | {back["critical_states"].get("current", 0)} | {back["critical_states"].get("stale", 0)} | {back["critical_states"].get("missed", 0)} | {back["receipt_to_advisory_s"]["p50"]:.3f} / {back["receipt_to_advisory_s"]["p95"]:.3f} / {back["receipt_to_advisory_s"]["p99"]:.3f} / {back["receipt_to_advisory_s"]["max"]:.3f} |

Current/stale labels come from each reading's own committed temporal decision, joined against the actually published public pressure samples and unchanged configured limit. A red latched event is not proof that every new reading was current. Receipt latency omits time spent before receipt; full acquisition-to-commit rows remain in the summary. Thus short receipt latency can coexist with stale mapped acquisitions.

Recovery stop-to-observed-ready: fast worker **8.568 s**, broker **7.069 s**, API **9.275 s**, database **10.959 s**. All previously stored event IDs survived these four checks. Exact queue/resource samples and actual browser timestamps are retained; no field-equivalent p99 assertion is made.

## Saturation and diagnosis

A separately labeled **10000 pending fixture-job fault injection** measured **10069 pending jobs** before two real authenticated MQTT publications. These fixture jobs are not 10000 fabricated sensor observations or a throughput benchmark. Both the ordinary and critical message received broker PUBACKs but were quarantined at the global durable admission limit; both are **missed at saturated admission**. Only the 10000 fixture rows were removed after testing. `phase7/queue_saturation.json` retains hashes, times and quarantine reasons. Critical worker priority cannot revive rejected messages or expired source time.

Measured constraints include serialized F1 state transitions, concurrent CPU contention, finite ingestion/worker service rate and unbounded accumulated trace histories. A longer drain deadline only permits observing recovery. The software retains and reports overload instead of weakening TTLs or asserting exactly-once delivery. A reserved, independently requalified critical admission/transport channel and representative hardware/load-envelope validation remain required work before closing P5-01.

Reproduction: deploy the explicit loopback overlays and run `scripts/phase7_e4_stress.py`, `scripts/phase7_e4_corrected.py`, `scripts/phase7_critical_boundary.py` and `scripts/phase7_queue_boundary.py` with new output paths. Do not run projects on conflicting ports. Original E4/E5 reports and seals remain unchanged.
"""
    write("PHASE7_E4_CORRECTED_STRESS.md", text)
    delta_s = (
        datetime.fromisoformat(recovery["started_at_utc"])
        - datetime.fromisoformat(first["started_at_utc"])
    ).total_seconds()
    delta_bytes = recovery["database_bytes"] - first["database_bytes"]
    idle_rate = delta_bytes / (delta_s / 3600)
    write(
        "PHASE7_STORAGE_VALIDATION.md",
        f"""# Phase 7 storage validation

**Actual backup/recovery PASSED; retention/capacity remains PARTIAL (P5-02).** Measurements use the Phase7 test database, including the first failed full stress attempt, supplementary streams and subsequent periodic idle assessments. They are not 90-day endurance or representative production sizing.

| Consistent snapshot | Observation rows | Total public table rows | Database bytes | Compressed dump bytes | Dump / restore seconds |
|---|---:|---:|---:|---:|---|
| Before raw archival | {first["source_tables"]["observations"]["rows"]} | {sum(v["rows"] for v in first["source_tables"].values())} | {first["database_bytes"]} | {first["dump_bytes"]} | {first["dump_s"]:.2f} / {first["restore_s"]:.2f} |
| After archival and overnight idle history | {recovery["source_tables"]["observations"]["rows"]} | {sum(v["rows"] for v in recovery["source_tables"].values())} | {recovery["database_bytes"]} | {recovery["dump_bytes"]} | {recovery["dump_s"]:.2f} / {recovery["restore_s"]:.2f} |

Both actual PostgreSQL custom-format `pg_dump` operations used an exported repeatable-read snapshot. Each restored into a new database; ordered canonical row checksums and counts match for **every public table**. Sixty recovered CAS artifact files match content-address hashes. The post-archive recovery independently copied and verified all **5120 raw archived messages**, including source digest and row identity. Dumps, CAS archives, raw archive objects, table/relation/index measurements and repeated API query times are in `phase7/storage_recovery.json`, `phase7/archive_recovery.json` and their raw output directories. Source databases were not replaced.

Optional bounded external archival moves only completed inbox rows: **{archive["archived_rows"]} rows**, **{archive["raw_bytes"]} bytes** → **{archive["archive_bytes"]} compressed bytes**. Durable content-hash objects are fsynced before the SQL deletion transaction commits. SQL keeps duplicate identity/digest, source, received time and archive row pointer. Pending jobs, scientific observations, evidence, events, provenance and explanations remain. Recovered samples replay as duplicates, and no pre-existing scientific row was deleted. Unit tests reject corrupted archives and protect unresolved work. The actual days=0 policy is an explicit accelerated lab test, not a claim of 90-day operation. Deployments must back up the archive directory together with SQL.

**Archiving raw inbox payloads does not solve F1 trace growth.** The second snapshot has 213592 trace rows with 984449313 logical JSON bytes; PostgreSQL TOAST/storage allocation means logical JSON size differs from physical database size. Ordinary vacuum/archival does not guarantee file shrinkage. No blocking `VACUUM FULL` or destructive history pruning was performed during stress. Periodic idle fusion also appends history; completed test workers were stopped after evidence capture to prevent continued test-only growth.

The observed mixed/idle snapshot interval was {delta_s / 3600:.2f} hours and grew by {delta_bytes} physical bytes: about **{idle_rate / 1024**2:.1f} MiB/hour**. Holding that particular rate fixed projects **{idle_rate * 24 * 90 / 1024**3:.1f} GiB/90 days**, before artifacts, replicas, indexes beyond this history mix, free space, backups or uncertainty. This is a rate extrapolation, not an endurance result or a bound for continuous active streams. Active throughput can produce much larger evidence/trace rates. Capacity approval requires a representative workload, long-horizon trace/event policy and measured storage headroom; the prior Phase5 projection is preserved as historical evidence.

Reproduce `scripts/phase7_archive_validate.py` and `scripts/phase7_storage_validate.py --output <new-output> --restore-name phase7_restore_<new> --archive-root <archive-store>`. The latter verifies all archived row identities after restore. Do not point restoration at the source database.
""",
    )
    write(
        "PHASE7_SECURITY_READINESS.md",
        """# Phase 7 security readiness

**Feasible laboratory checks executed; industrial/site commissioning remains BLOCKED/PENDING (P5-03).** The user confirmed no physical data or equipment is available. Local loopback identities, short-lived test certificates and simulation calibration authority are not approved site trust.

| Check | Actual result | Evidence |
|---|---|---|
| Authenticated MQTT source identity/topic ACL | Wrong credential rejected; wrong-source-topic message not persisted in full E4 | Full E4 report and raw broker/API observations |
| Malformed schema/asset/unit/source/future time/nonfinite | All six quarantined | `phase7/security_checks.json` |
| API RBAC and artifact boundary | Anonymous 401, viewer operator action 403, unknown artifact 404, unsafe/private bundle 422 | Same actual API checks |
| Application DB privileges | No superuser/createdb/createrole/replication/bypass-RLS flags; server-file read and role creation rejected | `phase7/database_privilege_checks.json` |
| HTTPS TLS | CA-verified protected endpoint 200; untrusted system CA rejected | `phase7/lab_tls.json` |
| MQTT TLS | CA-verified authenticated connection succeeded | Same, separate actual lab broker |
| OPC UA | Pinned-certificate Basic256Sha256 SignAndEncrypt read succeeded with source timestamp; write rejected BadUserAccessDenied; unencrypted connection rejected | Same; actual certificate-enabled server path |
| Dependency consistency/advisories | pip check passed; OSV query returned no advisories for 118 installed locked Python packages | `phase7/python_advisory_review.json` |
| Frontend advisory correction | Initial audit had 1 moderate and 2 critical development-tool findings; upgraded Vitest to 5.0.5; tests/build passed and follow-up audit has zero findings | `phase7/npm_audit_before.json`, `phase7/npm_audit_after.json` |
| Backup/artifact integrity | Canonical SQL rows, CAS files and 5120 archived messages verified after real restore | Storage validation report |

The first laboratory TLS attempt verified HTTPS but failed broker key access; the second also verified MQTT but failed OPC UA key format inference. Both failed reports remain. A third fresh run used appropriate protected PEM key files and passed the listed protocol checks. These are two-day self-signed **LAB ONLY** certificates, not industrial certificates. Lab broker root access was used only to read the protected bind-mounted test key; it is not a recommended site configuration. Private keys/tokens remain in gitignored `.edge` files; reports contain public results and hashes, not credentials.

Default demonstration HTTP/MQTT and optional NoSecurity OPC UA remain explicitly local-lab interfaces. The secure OPC UA server path is conditional on both certificate and key; a half-configured identity fails. Certificate trust/revocation, key rotation and storage, source-clock discipline, approved process limits, instrument calibration, operator account expiry/SSO, firewall review and site authorization remain uncommissioned. A clean advisory scan is time- and scope-limited, not a proof of security; no base-image/OS vulnerability scan is claimed. Field readiness is NO-GO until attributable site prerequisites are met.
""",
    )
    write(
        "PHASE7_INTEGRATED_DEMONSTRATION.md",
        f"""# Phase 7 integrated demonstration

Actual local browser and backend demonstrations; no physical flight, plant actuation or site-operator acceptance. Original analytics and F1 were used. Full E4 retest finished 6204 jobs; fresh reviewed reinspection and duplicate/restart checks followed on the isolated corrected stack.

| Case | Executed evidence | Result and boundary |
|---|---|---|
| D1 Normal monitoring | Three full E4 B1 normal streams, actual persisted trends | Normal input processed; scoped/unknown hazards are not blanket green |
| D2 Local deformation | Full B8 geometry plus fresh reviewed 20 mm software target | Reviewed result valid with **{inspection["regions"]} regions**; F1 **{inspection["F1_severity"]}** |
| D3 Thermal | Actual B8 thermal acquisition, worker and browser image | Numeric residual/image displayed; image-only association does not prove a 3D hotspot |
| D4 Critical without UAV | B7 pressure streams occur before first inspection job | Independent raw pressure can escalate; 18/186 stale in full run remains a timeliness failure |
| D5 Missing data | Protocol stop, 16 s wait, monitoring endpoint | Stale channels / no_recent_data / unknown_or_unavailable stored in B6 profile |
| D6 Plan → imperfect acquisition → F1 → replan | Fresh backend P0 recommendation, explicit simulation review, sealed requested pose, original sensing, import, job and P3v2 replan | Plan `{inspection["plan_id"]}`; inspection `{inspection["inspection_job_id"]}`; replan `{inspection["replan_id"]}`. No direct-control endpoint |
| D7 Inconclusive | Actual L2 inspection and heldout L2 failures | Inconclusive remains distinct from healthy; no forced detection |
| D8 Recovery without duplicate opens | Full service restarts preserve IDs; exact inspection envelope replayed twice around worker restart | **{browser["no_duplicate_event_open"]}** no new event IDs, one inspection job row, {browser["duplicate_audit_count"]} duplicate audit entries |
| D9 Unauthorized rejection | Live API/MQTT and malformed artifact tests | 401/403/422 and quarantines retained |
| D10 Displayed evidence audit chain | Actual Chromium model/assets/trends/inspection/thermal/geometric/monitoring/evidence/ack/reconnect checks | All twelve browser checks passed; screenshots/logs retained |

Fresh reviewed reinspection: `/mnt/d/TwinGuard/phase7-V7-reviewed-reinspection` contains frozen plan, plan-ready hash, actual public measurement bundle, linked result, F1 condition and replan. Browser/recovery: `/mnt/d/TwinGuard/phase7-V7-browser-and-recovery`. Full workload screenshots: `experiments/outputs/phase7-V4-full-E4-recovery-retest/browser`. Tracked compact records: `phase7/integrated_reinspection.json`, `phase7/integrated_browser_recovery.json`. The local test principal records software review only; no human/site approval is fabricated.

Reproduce with new output locations using `scripts/phase7_integrated_reinspection.py` and `scripts/phase7_integrated_capture.py`, against the explicit corrected loopback stack. The latter stops the completed test fast worker after capture to avoid unlimited idle-history growth.
""",
    )
    write(
        "PHASE7_TRL_ASSESSMENT.md",
        """# Phase 7 technology readiness assessment

**Conservative assessment: integrated software laboratory demonstrator, consistent with TRL 4 evidence for the tested software integration; industrial product TRL 5/6 is not established.** This is a documented internal assessment, not an independent certification or an averaged score across components.

The [NASA software/hardware TRL definitions](https://www.nasa.gov/pdf/458490main_TRL_Definitions.pdf) distinguish integrated critical software functions validated in a laboratory from end-to-end performance demonstrated in a relevant environment. Their [Earth Science Technology Office table](https://esto.nasa.gov/trl/) requires documented relevant-environment performance and scaling evidence for the higher software levels. TwinGuard's actual Docker protocols, durable processing, existing analytics/F1, planning and browser exercise integration, but do not establish physical instrument accuracy, industrial-edge timing or commissioned relevant-environment performance.

| Evidence category | Phase7 evidence | Readiness boundary |
|---|---|---|
| Synthetic software/research | Fresh measured virtual acquisitions, independent calibration and heldout seeds, common-detector planner comparison, acquisition ablations | Supports qualified laboratory software findings; candidate improvements can fail |
| External independent data | No verified external industrial/physical dataset supplied; prior dataset manifests are templates | PENDING; no external-data validation claim |
| Physical sensing/metrology | User confirms no data/equipment | BLOCKED; physical protocol records prerequisites |
| Relevant environment | Workstation/loopback, not intended edge hardware/site/network | PENDING; currentness/storage limitations remain |
| Commissioning | Local RBAC, lab TLS and readonly encrypted OPC UA tested | Site identities/limits/calibration/clocks/certificates/authorization remain PENDING |

A successful UI demonstration, optional laboratory certificates or clean tests cannot raise physical industrial readiness. Full stress includes stale critical readings and admission loss at saturation. View-domain abstention lowers false positives at substantial recall cost. Storage history continues to grow. These findings prevent unconditional deployment and research-superiority claims. TRL 6 is **not claimed**. Physical/site readiness is NO-GO pending the documented resources and independent relevant-environment evidence.
""",
    )
    print(
        "Operational reports and evidence copies written; final scientific summaries remain journal-gated."
    )


if __name__ == "__main__":
    main()
