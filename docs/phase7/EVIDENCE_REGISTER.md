# Phase7 evidence register

Detailed per-capability objective, source/version/git, data type, calibration, test, criterion, actual artifact hash, baseline, uncertainty and reproduction command are in [evidence_register.json](evidence_register.json). The status distinguishes test execution from research benefit and physical readiness.

| ID | Objective | Status | Evidence type |
|---|---|---|---|
| TG7-BASE | Retain and reproduce historical baseline | PASS | synthetic_software |
| TG7-GEO-DIAG | Diagnose view-dependent false positives | PASS scoped diagnosis | synthetic_software |
| TG7-CAL | Independent healthy view calibration | PARTIAL 12 of 20 domains | synthetic_software |
| TG7-DET | Independent common-measurement detector comparison | PASS evaluation; superiority NOT demonstrated | synthetic_software |
| TG7-PLAN | Fair five-planner paired comparison under two common detectors | PASS evaluation | synthetic_software |
| TG7-ABL | Execute six real-acquisition component ablations | PARTIAL component interpretation | synthetic_software |
| TG7-CONTROL | Missed-view, independent-obstacle, measured scoped-coverage controls | PASS execution | synthetic_software |
| TG7-E4 | Full corrected mixed-workload operational boundary | PARTIAL critical acceptance failed | synthetic_software |
| TG7-BACKLOG | Critical stream with measured ordinary backlog | FAIL timeliness | synthetic_software |
| TG7-CAPACITY | Expose saturated-admission loss | FAIL original critical admission | synthetic_software |
| TG7-RESERVE | Correct bounded current-critical admission | PASS boundary; full timing separately tested | synthetic_software |
| TG7-E4-FINAL | Full mixed workload after admission correction | PASS bounded full execution; mixed overload separately fails | synthetic_software |
| TG7-ARCHIVE | Preserve history while externalizing raw payloads | PASS bounded archive | synthetic_software |
| TG7-RESTORE | Actual SQL/CAS/raw archive disaster recovery | PASS tested recovery | synthetic_software |
| TG7-AUTH | Source, clock, schema, RBAC and artifact rejection | PASS lab scope | synthetic_software |
| TG7-TLS | Actual lab TLS and read-only encrypted OPC UA | PASS lab scope | synthetic_software |
| TG7-DEPS | Review and correct dependency findings | PASS checked scopes | synthetic_software |
| TG7-DEMO | Execute reviewed plan/acquire/F1/replan and real browser recovery | PASS software scope | synthetic_software |
| TG7-PHYSICAL | Independent surveyed LiDAR/thermal measurement validation | BLOCKED no equipment/data | physical |
| TG7-EXTERNAL | Independent external industrial data | PENDING no verified data | external_independent_data |
| TG7-RELEVANT | Representative edge/site operating environment | PENDING | relevant_environment |
| TG7-COMMISSION | Approved site trust, limits and instrument authority | BLOCKED/PENDING | commissioning |
| TG7-MIXED | Measure real inspection/critical overlap and failure boundary | FAIL 10x heavy timeliness | synthetic_software |
| TG7-TRENDS | Render actual stored values and reject obsolete asset responses | PASS | synthetic_software |
| TG7-FRESH | Acquire genuinely later scans after aged initial evidence | INCOMPLETE | synthetic_software |
