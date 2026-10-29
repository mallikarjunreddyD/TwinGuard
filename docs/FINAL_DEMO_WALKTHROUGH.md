# Browser-only demonstrator walkthrough

After one-time setup in [Simulation Lab](SIMULATION_LAB.md), open `http://localhost:19380` and sign in with the local operator token. There are no terminal commands in the normal demonstration flow.

1. Open Overview. Inspect the accepted reference model and actual asset conditions. Select an Unknown component and read its missing-evidence explanation.
2. Open Simulation Lab. Choose Healthy Operation, L1 and 2×. For a short first demonstration, leave inspections unchecked. Start and watch actual checkpointed/accepted counts increase.
3. Open Measurements from the session. Inspect stored values, units, quality and acquisition time. The session filter can be cleared to view all history.
4. Return to Simulation Lab. Pause and wait for controller acknowledgment. Published delivery count stops; source recency may persist briefly. Resume continues the same dataset/epoch.
5. Stop. The publisher ends; API, broker, workers and existing records remain. Stopping does not clear an advisory.
6. Choose Localized Deformation with inspections enabled. Start a fresh session. After the actual inspection job completes, open its LiDAR/thermal results. Interpret validity, regions and uncertainty; do not assume detection or global health.
7. Choose Critical Pressure. Inspections are disabled for this preset. Existing F1 evaluates current authoritative pressure independently of UAV input. Open Advisories and inspect supporting evidence. Acknowledge review as an operator and inspect the stored action/history; resolution remains governed by F1.
8. Choose Thermal Anomaly and then Degraded Sensing if useful. Keep image-only thermal scope and L2 insufficient geometry visible; neither is a reason to paint equipment healthy.
9. Choose Sensor Interruption. Its short real publication is followed by 16 seconds without data. Open Monitoring and distinguish missing source input from platform disconnection. Historical readings remain.
10. Inspect session history and reload the browser. State comes from the backend. A controller crash is explicitly failed/reviewable; Restart creates a fresh session rather than silently replaying old observations.

Viewer tokens can inspect history but cannot execute scenarios or acknowledge reviews. Site-review mode cannot run demos. Physical equipment, calibrated instruments, commissioning and relevant-environment validation remain outside this software demonstration. The optional site-profile verification deployment is a lab test, not a physical site.
