# Final software-demonstrator UX validation

Decision: **CONDITIONAL GO** for the software-demonstrator UX release. All executed software acceptance checks pass. Criterion 24 remains PARTIAL because the separate original archive workflow exited with `OSError: [Errno 12] Cannot allocate memory` during `os.sendfile` from D:. This task did not signal, restart or modify the archive workflow or its inventory, CAS objects or source roots. Its completion remains unresolved; current memory availability cannot establish the cause at failure. This is not physical validation, a new scientific result or an industrial-readiness claim.

Validated on 2026-10-29 in the isolated `/home/mallikarjun/workspace/TwinGuard-demo-ux` worktree, branch `phase-7-demo-ux-finalization`, source baseline `6392d886c161b981e1093cbc157f9f1e2d129369`. Original scientific freeze: `edae1e5`. Running deployment: `twinguard-demo-ux`, dashboard <http://localhost:19380>. The original `phase-7-release-finalization` checkout remains clean at the baseline commit. The review-profile test on port 19390 uses only the isolated laboratory database; it does not represent site commissioning.

## A. Architecture

The production API contains public bounded session contracts and authenticated command/status routes; privileged dataset generation is in a separate optional controller image. Durable PostgreSQL sessions, command keys, unique namespace ownership and controller advisory locks enforce lifecycle/idempotence and a single publisher. The controller uses the existing generator, MQTT ingestion, inspection worker and F1 pipeline. It never inserts observations/evidence/events directly. API/frontend have no private demo dataset mount or Docker socket. See [controller architecture](SIMULATION_CONTROLLER_ARCHITECTURE.md).

Unexpected controller restart fails the owned interrupted session, retains its checkpoint and does not replay it automatically. An in-flight delivery may already have committed. Stop ends the session publisher and retains the platform, observations and advisories. Restart creates a fresh identity. User commands cannot select executable names, shell strings, paths, physical endpoints or calibration trust.

## B. Actual browser lifecycle

[Final lifecycle evidence](demo-ux/browser-lifecycle.json): **11 checks passed**, errors empty. Healthy session `demo-05ab79933db0510d9fe15a234517696b`, L1, 2x, no inspections: 24 actual public MQTT envelopes observed, 24 checkpointed broker-acknowledged deliveries, 24 unique accepted sensor observations. The test observed stable broker counts while paused and stopped, resumed the same session/epoch, plotted stored measurements after Stop, refreshed the browser to recover durable state and confirmed authenticated platform health plus a live broker connection.

Original acquisition timestamps and values remain unchanged. Replay mappings, rate, emission and receipt clocks are explicit. Actual pause duration shifts the declared replay mapping; queue backpressure does not rejuvenate measurements. PUBACK, edge acceptance, inspection completion and evidence qualification are distinct statuses.

## C. Dashboard and accessibility

The light-neutral, graphite/steel-blue visual system uses maintained CSS variables, labeled severity, explicit Unknown/missing-requirement explanations, source recency separate from platform/publisher connectivity, real stored charts and expandable audit rationale. No condition is hardcoded healthy and no advisory is cleared for presentation. The accepted 3D model retains actual geometry, selection, orbit/zoom/pan and measurement/planning overlays.

[Final live audit](demo-ux/final-runtime-audit.json): all seven pages exercised, no page errors, console errors/warnings, HTTP errors or failed requests during the normal sweep. Real Tab focus visibility and ArrowRight equipment selection passed. Overview has no horizontal overflow at 1500, 850 and 390 px; Simulation Lab has no overflow at 850 px. Main controls use 44px minimum height. Computed token contrast against white/canvas ranged **4.57:1–11.80:1**, with secondary text 5.73:1 and amber 4.90:1. These are scoped browser checks, not a complete WCAG certification or assistive-technology audit.

## D. Executed scenarios and recovery

[Scenario counts](demo-ux/scenario-counts.json), [actual scenario/recovery evidence](demo-ux/scenario-and-recovery.json) and [ingestion reconciliation](demo-ux/ingestion-audit-counts.json) retain IDs and outcomes. Counts below are checkpointed deliveries / unique accepted sensor rows / completed inspection jobs. Completed does not mean qualified or fault-confirming.

| Preset | Deliveries | Sensor rows | Inspection jobs | Actual result |
|---|---:|---:|---:|---|
| Healthy, stopped by browser | 24 | 24 | 0 | Start/Pause/Resume/Stop; stored chart retained |
| Critical Pressure, stopped after event | 161 | 160 | 0 | F1 red critical-pressure event without UAV corroboration; actor/rationale acknowledgment retained without resolution |
| Localized Deformation L1 | 434 | 428 | 1 | Geometric status valid, one localized geometric region; thermal results include inconclusive and valid |
| Thermal Anomaly L1 | 434 | 428 | 1 | Thermal results include inconclusive and valid; one extra geometric region also retained |
| Degraded Sensing L2 | 380 | 373 | 1 | Geometric insufficient_coverage, zero geometric regions; thermal results include inconclusive and valid |
| Sensor Interruption | 80 | 80 | 0 | 16 actual wall-clock seconds without publication; real source monitor becomes unavailable |

For critical, one source-record duplicate was audited. Each L1 inspection run includes one inspection delivery and five duplicate sensor observations; L2 includes one inspection delivery and six duplicates. Existing idempotent ingestion retained unique sensor rows; no quarantines occurred in this lab snapshot. The thermal preset's extra geometric region is not suppressed and is not reported as a confirmed structural fault or accuracy improvement. Image findings do not establish verified 3D association.

Ten scenario/recovery checks passed. Actual controller restart produced a failed interrupted session with no silent republication. Actual API/frontend restart retained sessions, observations and event identities. Viewer execution and operator execution in `site-review` were rejected with 403 in both browser/API tests, even with the demo enable flag set. The original scenario harness stopped after five successful cases on an optional `phase` polling KeyError; the recovery report explicitly references that failed attempt by SHA256, retains those actual cases and executes the remaining cases. It does not relabel the initial attempt as passing.

A real P3 request ran through the planning worker and returned one recommended viewpoint with **2.431 m² predicted new usable reference area**. The accepted model, recommended positions and coverage/rejection overlays rendered. This is a predicted software recommendation, not measured coverage, physical flight or a planner-performance claim. Actual plan ID/snapshot/policy hashes are in the final live audit.

## E. Screenshots and correction pass

All 26 PNGs under [screenshots](demo-ux/screenshots/) are captured from running applications, without invented values or compositing. Exact repository-relative paths:

- Before desktop: `docs/demo-ux/screenshots/before-overview-desktop.png`
- Before responsive: `docs/demo-ux/screenshots/before-tablet.png`
- First pass: `docs/demo-ux/screenshots/first-pass-overview.png`
- After desktop: `docs/demo-ux/screenshots/after-overview-first.png` (final harness captured this name)
- After running/paused lab: `docs/demo-ux/screenshots/after-simulation-running.png`, `after-simulation-paused.png`
- After responsive lab: `docs/demo-ux/screenshots/after-tablet.png`
- Real generated plan: `docs/demo-ux/screenshots/after-plan-generated.png`
- Critical advisory, L1/L2 inspections, interruption and disabled site-review screenshots are retained beside them.

The before capture includes its actual loading state and is not a controlled numerical comparison. [Explicit visual correction pass](demo-ux/VISUAL_CORRECTION_PASS.md) records the reviewed first pass and corrections to empty chart axes, duplicate labels, repeated missing-evidence prose, focus targets and chart text. Final desktop, tablet and generated-plan images were visually inspected after correction.

## F. Tests and reproducibility

Actual logs are preserved under [checks](demo-ux/checks/):

| Check | Executed result |
|---|---|
| Full backend regression suite | **362 passed**, 734.06 s |
| Final focused lifecycle/replay tests | **15 passed**, 38.72 s; included in full-suite count, not 15 additional distinct tests |
| Ruff | All checks passed across src/tests/scripts |
| Ruff format | 204 files already formatted |
| Mypy | No issues in 118 source files |
| Frontend Vitest | 3 passed |
| TypeScript + Vite production build | Passed; bundle >500 kB warning remains |
| Compose simulation + review overlay | `config --quiet` passed |
| Real browser/MQTT lifecycle | 11 checks passed |
| Scenario/recovery integration | 10 checks passed, including five explicitly retained from initial run |
| Final live planning/pages/contrast/isolation audit | 8 checks passed |

Pytest retains one existing Starlette/httpx deprecation warning. The full suite preceded the final read-only event-history endpoint, standard-library uploader adjustment and UI polishing; the final focused suite, Mypy/static checks, frontend build and actual inspection uploads/browser workflows cover the final changes. No new scientific algorithm tests or performance claims are introduced.

Re-run against a provisioned isolated lab:

```bash
export PYTHONPATH=src TWINGUARD_ROOT="$PWD"
python -m pytest -q tests/test_demo_sessions.py tests/test_demo_replay.py
python scripts/demo_ux_browser.py --output .demo-data/browser-repeat
python scripts/demo_ux_scenarios.py --output .demo-data/scenarios-repeat
python scripts/demo_ux_final_audit.py
```

Use an environment with the project's development dependencies and Chromium installed. The case scripts use the ignored local credentials, actual local MQTT and running services; recovery tests intentionally restart only their named demo controller/API/frontend. Never point them at the original archival project or a physical/site deployment. Full scenarios generate new identities and consume retained demo storage; the session bound is 200 pending administrator review.

Retained earlier attempts, including initial packaging failure, stale-session test binding, a keyboard test probe error, an overly strict named-user assertion and a Playwright launch failure, are documented in `demo-ux/retained-attempts.json`, the first/second runtime-audit JSONs and `controller-initial-failure.json`. Final passing reports are separately named. No failed test run is promoted to success.

## G. Security and scientific integrity

[Integrity audit](demo-ux/integrity-and-archive-audit.json) compares **161 tracked scientific/configuration/scenario/experiment files** with the source baseline in both worktrees: zero differences. The original checkout is clean and its branch/HEAD unchanged. Scientific detector/fusion/planner logic, calibration models, thresholds and historical validation reports are unchanged. The sole ingestion addition is optional operational demo-session metadata; existing qualification, QoS, priority and F1 decisions remain intact. Existing OPC UA and MQTT processing regressions pass; this task does not claim a new physical OPC UA validation.

Runtime API checks show `twinguard.demo`, `plant`, `sensing` and `evaluation` absent. Actual UID is 10001 for API/controller, neither mounts Docker socket, and only the controller mounts private `/demo-data`. Controller limits: 0.75 CPU, 1536 MiB, 96 PIDs; one generator, 180 s preparation timeout, 512 MiB dataset bound, 10,000 publication records. The `tg_simulation` database role is not superuser and cannot create databases/roles; it can read/update demo sessions and read jobs but cannot insert observations or update scientific records. Controller credentials are a dedicated uploader principal, not an exposed operator token. Site-review browser controls are disabled and server enforcement is independent.

## H. Archive safety and remaining blocker

All task edits, demo datasets/volumes and UI evidence were isolated outside original archive source roots. The original repository remains clean at `6392d88`. No original archive process was terminated or restarted and no original source, inventory or content-addressed object was modified by this task. The recorded error is preserved read-only in the integrity audit. Nevertheless the archive workflow is no longer running and remains partial after its allocation failure. Archive completion requires a separately authorized recovery task; UX completion does not certify it.

## I. Documentation and walkthrough

Start with [browser demonstration walkthrough](FINAL_DEMO_WALKTHROUGH.md), [Simulation Lab installation and semantics](SIMULATION_LAB.md), [architecture](SIMULATION_CONTROLLER_ARCHITECTURE.md) and [redesign report](FINAL_DASHBOARD_REDESIGN.md). README, DASHBOARD_GUIDE, DEMO_WALKTHROUGH and PHASE5_ARCHITECTURE link this additive software work. Historical Phase 5/6/7 validation reports were preserved.

## J. Acceptance decision

| # | Criterion | Status | Evidence / limit |
|---:|---|---|---|
| 1 | Dedicated Simulation Lab page | PASS | Live seventh navigation page |
| 2 | Functional scenario selection | PASS | Six presets executed through browser/backend |
| 3 | Backend Start/Pause/Resume/Stop | PASS | Actual MQTT observer and durable state |
| 4 | Isolated controller/API/evaluator boundaries | PASS | Runtime module/mount and DB-role audit |
| 5 | Persistent, idempotent sessions | PASS | Lifecycle tests, unique ownership, restart tests |
| 6 | Existing MQTT/OPC UA analytics and F1 unchanged | PASS | Scientific comparison and full regressions; operational metadata only |
| 7 | Valid timestamps/replay clocks | PASS | Explicit mapping, focused pacing tests and real publisher workflow |
| 8 | Actual progress | PASS | Broker checkpoint, SQL rows and real jobs separately labeled |
| 9 | Connectivity explanation | PASS | Source recency/platform/publisher distinction and real interruption |
| 10 | Correct Unknown conditions | PASS | Actual missing requirements; no inferred healthy state |
| 11 | Existing pages functional | PASS | Seven-page live sweep, zero normal-phase network/console failures |
| 12 | Professional redesign | PASS | Real before/after images and explicit correction pass |
| 13 | Maintainable tokenized CSS | PASS | CSS variables and readable source |
| 14 | Readable text/charts/status | PASS | Scoped contrast checks and visual inspection |
| 15 | Accessibility/responsiveness checks | PASS | Real Tab/Arrow interaction, 1500/850/390 overview and 850 lab checks; not complete WCAG certification |
| 16 | Actual 3D geometry/overlays | PASS | Loaded model, selection, localized measured region and actual generated-plan overlays |
| 17 | Browser-only new scenario workflow | PASS | Browser Start/restart with fresh persistent identity |
| 18 | Authentication/role restrictions | PASS | Viewer and restrictive-profile 403 tests, existing auth regression |
| 19 | No physical control/arbitrary execution API | PASS | Bounded preset/config contracts and route review |
| 20 | Historical methods/results unchanged | PASS | 161-file baseline comparison, original clean checkout |
| 21 | Existing backend/frontend tests | PASS | 362 backend / 3 frontend; static/build/Compose pass |
| 22 | New controller/browser tests | PASS | Focused 15 plus actual integration reports |
| 23 | Real screenshots | PASS | 26 actual PNG captures, final visual review |
| 24 | Archive construction/evidence unaffected | PARTIAL | No task mutations/signals; scientific files unchanged, but original archive exited ENOMEM and completion is unresolved |
| 25 | Reproducible walkthrough | PASS | Installation guide and browser workflow |

**24 PASS, 1 PARTIAL, 0 FAIL. CONDITIONAL GO** for this software UX branch. The archival release remains incomplete. No physical instruments/data were available; no metrological accuracy, TRL promotion or industrial-safety readiness is claimed.
