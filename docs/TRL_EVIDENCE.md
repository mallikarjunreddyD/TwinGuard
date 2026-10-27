# Evidence register

No unsupported TRL rating is assigned. The objective is a TRL-6-oriented demonstrator; software simulation alone cannot establish TRL 6 for the full industrial hardware/software product.

| Evidence class | Status | Evidence/next requirement |
|---|---|---|
| Previously demonstrated PI technology | Unverified | Obtain publications, reports and deployment records; none supplied here |
| Implemented TwinGuard infrastructure | Implemented | Source, schemas and tests; execution outcomes in VALIDATION.md |
| Synthetic-data experiments | Pending | Phase 1 simulator arithmetic/geometry validation is implemented (PHASE1_VALIDATION.md); sensor/algorithm accuracy experiments are pending |
| Independent public-dataset validation | Pending | Select licensed source, preserve provenance, run independent held-out evaluation |
| Physical sensing validation | Pending | Hardware, calibration, synchronized acquisitions and reference instruments |
| Industrial relevant-environment validation | Pending | Representative site, engineering approval, installation, repeatable trials and measured acceptance criteria |

Every future evidence entry must link date, responsible owner, dataset/software/configuration versions, environment, procedure and immutable result artifacts. Capability declarations are infrastructure inventory, not experimental findings.

## Phase 1 evidence

Implemented seven-asset parametric geometry, load-driven operating states, axial expansion, actual mesh displacement/support translation/temperature-field/process faults, independent truth snapshots and replay artifacts. Numerical comparisons and resource measurements are recorded in PHASE1_VALIDATION.md and its referenced JSON. These validate the code under stated surrogate assumptions. They do not validate physical boiler dynamics, industrial sensing accuracy, defect classification or TRL 6. Previously demonstrated PI technology remains unverified; public-dataset, hardware and relevant-environment validation remain pending.


## Phase 2 virtual-sensing evidence

Implemented and tested Open3D CPU first-hit LiDAR/thermal visibility, radiometric vertex interpolation, configurable noise/pose uncertainty, nine-channel IoT sampling and replay transport effects. Numeric comparisons, actual measured plots and repeat-order evidence appear in PHASE2_VALIDATION.md and phase2_sensing_validation.json. Known-plane/occlusion checks establish numerical correctness under the model; comparisons to assumed noise/radiometric references establish synthetic consistency only. They do not establish physical sensor calibration, commercial instrument accuracy, industrial fault-detection reliability or TRL 6. Independent public-data and physical/relevant-environment validation remain pending. E1–E4 remain not_implemented.


## Phase 3 update

Phase 3 software evidence: actual CPU Open3D registration, patch geometric screening, numeric thermal residual regions, healthy-only dynamic operating fits, truth-isolated inference and full synthetic E1/E2 comparisons are implemented. See PHASE3_VALIDATION.md and its 154-pair/30-sequence records. This demonstrates controlled software functions, with limited small-change sensitivity and qualified missing/OOR handling. It is not independent physical accuracy or a new TRL assignment. E3 fusion and E4 integration are still pending.
