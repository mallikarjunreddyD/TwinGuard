# Phase 7 release readiness

**Release packaging: PARTIAL. Software checks: PASS. Research validation remains conditional.**

The branch is `phase-7-release-finalization`, created from `abf5d8d488236913a88b71fd2fd1937943712c3a`. Scientific source, calibration and policy matches are recorded in [scientific integrity](release/SCIENTIFIC_INTEGRITY.json). No B3.1/B3.2/F1/P3/P3v2, simulator, sensing noise, thresholds or 10-second freshness rule changed.

The historical formatting failure in `docs/phase7/software_checks.json` is retained. The existing `phase7_write_reports.py` already passes formatting; no unnecessary correction was applied and the report generator was not rerun. Fresh actual commands, timestamps, exits and outputs are in [release checks](release/RELEASE_CHECKS.json).

| Requirement | Status | Actual result / limit |
|---|---|---|
| Branch | PASS | Requested release branch from supplied SHA |
| Scientific integrity | PASS | Frozen scientific files/configurations match; other infrastructure differences disclosed |
| Ruff lint and format | PASS | Both independently executed; final formatting 193 files |
| Pytest | PASS | Existing suite 336 passed, one deprecation warning; eleven new archive tests separately passed |
| Mypy | PASS | 114 source files |
| Frontend | PASS | Three tests; TypeScript/production build; bundle-size warning retained |
| API | PASS | Actual backend JSON health; initial frontend HTML fallback explicitly not counted as API health |
| Compose | PASS | Base and Phase 7 overlay validated; wrong initial path failure retained |
| Archive inventory | PARTIAL | Repository root counts recorded; external native scan complete; full copying pending |
| SHA-256 integrity | PARTIAL | Builder journals individual copied files; full independent verification pending |
| Restoration/corruption | PASS bounded | Three real objects independently restored; isolated corrupted copy rejected; eleven builder/path/secret/reference tests |
| Reproducibility | PARTIAL | Utilities and compact manifest created; whole-archive checksum pending |
| Secret exclusion | PARTIAL overall | Builder exclusion and independent verifier implemented/tested; full archive scan pending |
| Proposal and traceability | PASS scoped | 1,284 prose words excluding table; preserved numerical evidence and limitations |
| Outstanding issues | PASS retention | All unresolved P5/P6 findings remain open/partial/blocked |
| Physical claims | PASS restraint | No physical TRL 6 or safety certification claim |

Original experiments/reports were not overwritten or rerun. Release scripts, archive tests, ignore rules, proposal/traceability and release metadata are the intended changes. Incorrect initial verification commands remain in the log with corrected checks rather than disappearing. Existing Starlette/httpx and frontend bundle warnings remain nonblocking.

The complete raw collection is substantially larger than the prior migration subset. Archive construction is ongoing; **no full-archive PASS or release push is claimed while it remains unverified**. See [archive verification](release/ARCHIVE_VERIFICATION.json), [inventory](release/ARCHIVE_INVENTORY.md), [reproduction guide](REPRODUCIBILITY_GUIDE.md), and [proposal](PROPOSAL_TECHNICAL_EVIDENCE_SUMMARY.md).

Heavy-load critical staleness, trace growth, site commissioning, physical LiDAR/thermal validation, cross-view support, unequal multi-asset calibration and mixed planner discovery remain unresolved. Packaging PASS, when eventually verified, will not close these research limitations or establish industrial readiness.
