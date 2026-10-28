# Phase 6 architecture

Software 0.7.0 extends the Phase 5 advisory platform. The starting commit is 5ed9f031a58ad7f36a498c064d1359a0a2815082 on phase-5-edge-platform; the implementation branch is phase-6-risk-adaptive-inspection. Baseline: 266 tests passed. The first executable candidate was committed as 1779975 before held-out execution.

Public SQL condition/event/coverage records → frozen PlanningSnapshot → accepted-map candidate generation → nominal raycasting → modality suitability and static feasibility → P0/P1/P2/P3 selection → immutable plan artifact and SQL index → authenticated dashboard/review. A separate privileged experiment controller reads a frozen plan, requests original imperfect Phase 2 sensing, exports public observations, runs unchanged B3.1/thermal and F1, updates public coverage and replans. Evaluator labels never enter inspection modules.

The inspection package contains contracts, observations, coverage, visibility, candidates, feasibility, priority, utility, optimizer, replanning, explanation, qualification and CLI modules. edge/planning.py runs dedicated leased jobs with bounded pending capacity eight, three retry attempts, a 300-second lease, one CPU and 2 GiB container limit. It never acquires the F1 checkpoint lock. FastAPI handlers freeze input records and enqueue; they do not raycast. Plan JSON and cell geometry use content-addressed artifact storage. SQL contains request/snapshot lineage, compact plan indexes, review audit and job state. Migration 0002 adds the job kind/status/creation index.

Original plant, sensing, analytics and fusion implementations remain unchanged. Phase 5 inspection workers add a downstream registered-public-cloud coverage product. Missing/invalid registration never becomes qualified coverage. No planning operation changes an F1 assessment or resolves an advisory.

Read PHASE6_VALIDATION.md for actual execution and limitations. See PHASE7_VALIDATION_BACKLOG.md for preserved OPEN concerns.
