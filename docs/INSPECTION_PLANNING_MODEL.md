# Inspection planning model

All public records use schema 1.0.0, explicit identifiers and UTC. InspectionPlanningRequest sets method, maximum views (1–12), seconds, travel meters and per-asset limit. PlanningSnapshot binds causal public asset states, source IDs, reference hash, actual coverage, previous plan and attempted views. Unknown stays unknown. A latched red event remains red context when instantaneous monitoring expires.

Criticality is configured in configs/inspection/planner.yaml; it is never inferred from asset names. Missing criticality uses an explicitly explained neutral 0.5 and requires review. Current severity is mapped green=0, amber=0.6, red=1, unknown=0.5 solely for an engineering score. Confidence, access and evidence need remain separate.

Priority = 0.15 criticality + 0.20 severity + 0.30 deficiency + 0.15 freshness + 0.10 reinspection + 0.10 unsuccessful attempts. Each term is bounded [0,1]. Freshness=min(1, age/3600 s), missing history=1. Failed attempts=min(1,count/3). Deficiency=max(1−fresh qualified modeled-area fraction, 1−confidence when required evidence is missing). This is not a probability of failure or a calibrated information posterior.

AssetInspectionPriority stores every subscore and reason. CandidateViewpoint stores a planned Transform, sensor/calibration references, range, incidence, area cells, sampling proxy, registration return support, feasibility, costs and utility. InspectionPlan binds request, snapshot and policy hashes, steps, order, budget, marginal areas, advisories, explanation and pending operator review. PlanningEvaluationRecord is distinct from operational input. Planned, reported and controller-private actual poses are different records.
