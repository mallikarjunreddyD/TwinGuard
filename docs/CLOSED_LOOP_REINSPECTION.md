# Closed-loop software reinspection

The controller is evaluation/inspection_experiments.py, outside the production planner boundary. Each trial generates actual imperfect initial public scans, runs unchanged B3.1 and F1, and freezes a shared planning snapshot. Every method's plan JSON and SHA256 manifest precede its requested acquisition. The Phase 2 sensor receives the selected planned sensor-local→world pose; its actual pose remains controller-private and its noisy reported pose is exported separately. Public NPZ arrays retain measured noise, dropout and sensor resolution. No ideal oracle point cloud substitutes for acquisition.

Existing analyze_geometry(..., methods=["B3.1"], improved_calibration=frozen_model) processes each new scan against the initial measured baseline. Original thermal inference handles supported thermal views. Original fusion adapters and assess() update F1 without resolving physical faults. Coverage uses the saved registered measured NPZ and valid patch qualifications. Failed/inconclusive scans increment unsuccessful history and remain visible.

P3 executes a causal next-view recommendation after each public update, subject to the original remaining view/time/travel budgets and another actual segment check. Replans and their hashes are saved before subsequent sensing. P0/P1/P2 execute their frozen sequences for comparison. The F1 checkpoint, public snapshots, executed-step records and raw observations are retained. Plan IDs and source references link cycles. Evaluation truth is read only after per-method plan/result sealing.

This is a synthetic inspection loop. API review authorizes software simulation only; there is no UAV execution endpoint. No process condition or advisory severity is changed by planning.
