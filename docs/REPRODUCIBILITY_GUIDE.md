# Reproducing and restoring TwinGuard evidence

Git preserves code, public configurations, reports and compact evidence. It does **not** contain the complete raw datasets. Independent reproduction requires the separate research archive or original local experiment roots, the recorded source revision, locked dependencies, and sufficient storage/compute. Physical experiments additionally require instruments and approved facilities; none have been executed.

## Locations and boundaries

The authoritative original roots include the repository's `experiments/outputs`, `datasets`, `configs`, and `docs`, plus the independent Windows archive `D:\TwinGuard` (`/mnt/d/TwinGuard`). Ubuntu's registered backing store is `E:\WSL\Ubuntu-24.04`; that registration does not relocate D:. The earlier `experiments/outputs/external-phase7` copy has no completed independent verification ledger and must not be treated as authoritative. Original D: content is preserved.

The versioned release archive is configured with `--destination`; this execution uses `experiments/releases/phase7-release-finalization-v1` inside the E:-backed Linux filesystem. It is outside Git. `docs/release/REPRODUCIBILITY_MANIFEST.json` points to the external detailed manifest and its checksum. Consult `ARCHIVE_VERIFICATION.json` for the actual complete/partial state, not merely the existence of the destination.

## Build, resume and verify

Run from the repository using its virtual environment. Example roots can be relocated; retain the portable root identifiers:

```bash
.venv/bin/python scripts/release/build_evidence_archive.py \
  --destination /chosen/archive/phase7-v1 --revision <source-sha> \
  --root outputs=experiments/outputs --root datasets=datasets \
  --root configs=configs --root source=src --root reports=docs \
  --root external=/mnt/d/TwinGuard
# Add --resume to reuse verified existing objects after interruption.
.venv/bin/python scripts/release/verify_evidence_archive.py \
  /chosen/archive/phase7-v1 --manifest manifest.release.json --report /chosen/verification.json
```

After building, run `finalize_evidence_archive.py <archive> --release-source-git <tested-sha>` to append `manifest.release.json` and an enriched inventory without overwriting the build records. The independent verifier then checks required references and archived scientific freeze metadata.

The archive uses SHA-256 content-addressed objects and a logical per-file JSONL inventory. Identical data share an object within their disclosure class; restricted evaluator truth is separate from public research records. Credentials, private TLS identities, runtime environment secrets, caches, dependencies and build products are excluded. Conservative credential-like exclusions may omit diagnostic fixtures; consult the exclusion ledger. The research archive is never a runtime/frontend input bundle. Null run metadata is unknown: packaging Git is not a substitute for original run provenance. Preserved `campaign.json`, configuration, source manifests, prediction seals and evaluator journals establish the detailed producer/configuration/seed relationships.

Verification independently recalculates inventory/object hashes and counts, rejects duplicate logical paths, traversal and symlink escapes, and checks sensitive content. Compare scientific source/configuration records with `SCIENTIFIC_INTEGRITY.json` and the archived Phase 7 freeze. Incomplete campaigns retain their status; a failed attempt is not superseded out of existence by a successful retest. Original files remain until verification, and this task does not delete them afterward.

## Restore a selected file or dataset

Find records with the desired `source_root` and relative `path` in `files.jsonl`. Copy each record's `object_path` from the archive to a fresh restoration directory using its logical relative path. Reject absolute paths, `..`, drive prefixes and symlinks; verify SHA-256 and byte count again after restoration. Restricted-evaluation records belong in separate evaluator-only storage. Do not flatten roots: identical relative paths in different roots remain distinct logical identities. Never overwrite original datasets during restoration.

## Select code, configuration and experiments

Use the original experiment's source/configuration/calibration hashes and Git revision from its sealed journals. Phase 7's scientific candidate freeze is `edae1e5`; final chronology packaging is `abf5d8d`. E3's verified producer is recorded in `docs/phase4/final_revision.json`, and E5's in `docs/phase6/final_revision.json`. An unknown older producer SHA must remain unknown until recovered from its original journal. Locked package versions matter, especially numerical geometry dependencies. Timing, generated identifiers and floating-point ties can vary; do not interpret byte-level differences in timestamps as scientific changes.

For an independent new run, use **new output directories**, not archived originals:

```bash
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
.venv/bin/twinguard experiment run E1 --config experiments/E1.yaml --output-dir /new/E1
.venv/bin/twinguard experiment run E2 --config experiments/E2.yaml --output-dir /new/E2
.venv/bin/twinguard experiment run E3 --config experiments/E3.yaml --smoke --output-dir /new/E3-smoke
.venv/bin/twinguard experiment run E4 --config experiments/E4.yaml --output-dir /new/E4
.venv/bin/twinguard experiment run E5 --config experiments/E5.yaml --output-dir /new/E5
.venv/bin/twinguard experiment report --run-dir /new/E1
```

E4 requires the documented local Docker services, authenticated lab configuration, explicit loopback ports and public input preparation; its command is not a hardware-free substitute for service commissioning. Consult `EXPERIMENT_E3.md`, `EXPERIMENT_E4.md`, `EXPERIMENT_E5.md`, and the original validation reports for prerequisites, development versus evaluation seeds and interpretation. Smoke runs check execution, not reproduction of full metrics. No full E1–E5 campaigns were rerun for this release task.

Original E1–E5 reports remain distinct from Phase 3.1 corrections and Phase 7 held-out evaluations. Their distributions and matching semantics differ. Unknown, inconclusive and unexecuted results remain explicit. Equipment-dependent geometric metrology, radiometric calibration, physical process instrumentation, site clocks/security/limits, flight authorization and representative-environment validation remain pending; archive integrity does not establish physical TRL 6.
