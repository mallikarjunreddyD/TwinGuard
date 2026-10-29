# Final dashboard redesign

This is a demonstrator UX enhancement, not a new research-performance claim. The reference geometry, detector/planner math, sensor noise, calibration, F1 policy and frozen experimental outputs are unchanged.

## Visual system

Warm off-white canvas, white surfaces, graphite text, restrained steel-blue interaction, and labeled red/amber/green/unknown states replace the dark cyan-heavy theme. CSS variables define palette, typography, spacing and component boundaries. Native controls and existing React/Three.js/Recharts are retained; no heavy UI framework or cloud font dependency is added. Text is readable, controls have keyboard focus and at least 44-pixel height, and charts retain units and genuine data gaps.

The sidebar contains seven actual destinations. Deployment/advisory/no-plant-control information is separate from navigation. Overview prioritizes accepted geometry, actual condition counts and the selected asset; other pages are not burdened by repetitive summary cards. Three.js orbit/zoom/pan, selection, estimated-region and planning/FOV overlays remain; only presentation, contrast and keyboard selection feedback changed. Geometry is explicitly the accepted reference, never a live measured deformation mesh.

## Evidence interpretation

Unknown is preserved and explained using actual missing requirements and rationale. Severity is separate from qualification. Monitoring distinguishes source receipt, quality, calibration and clock basis; the source header is clickable and explains why zero recent sources can coexist with a healthy platform. Stored telemetry remains after a publisher stops, with source time, receipt-time display, units, quality, residual/reference and illustrative limits kept distinct. Empty and unsupported measurements do not become fabricated values.

Inspection views show real B3.1/thermal reports, including insufficient coverage. Advisory review exposes stored supporting evidence, current missing requirements and real operator/lifecycle history. Acknowledgment is not resolution. Planning retains predicted-versus-qualified coverage and review-only route semantics; Simulation Lab presets are not physical route execution.

## Visual verification and corrections

Before screenshots and first-pass rendered screenshots are preserved under `docs/demo-ux/screenshots`. The explicit correction review is in `demo-ux/VISUAL_CORRECTION_PASS.md`: empty-limit-only axes were removed, duplicate identity/missing-evidence text simplified, controls enlarged and chart labels improved. Final desktop/tablet captures and validation reports document the executed interface. Before/after appearance comparisons are not controlled scientific comparisons: they use different isolated operational datasets and loading states.
