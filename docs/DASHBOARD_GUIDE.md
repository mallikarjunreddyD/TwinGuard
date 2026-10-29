# Dashboard guide

The running application is served at http://localhost:18780 by the local Compose stack. It consumes authenticated backend records and SSE; it does not generate detections, risk scores or timed status animations. Use the locally generated viewer/operator/admin token from .edge/secrets.json. Session tokens stay in the current browser session. Do not publish tokens in screenshots or shell logs.

## Overview

The overview identifies the plant, deployment profile and policy. Platform-stream connectivity is shown separately from recently received sources. Counts include unknown asset conditions; no alert does not imply healthy equipment. The accepted baseline GLB is an as-built model, not a measured deformation animation. Orbit/zoom/pan and asset selection drive scoped details. The asset strip provides a keyboard/button alternative to 3D selection.

Severity and confidence are separate. Gray means unknown. A qualified wall patch never establishes whole-equipment health. Amber boxes denote estimated localized measurements; original geometry stays intact. Acquisition time, baseline/current capture IDs, model version and quality remain available in inspection/evidence views. Display normals/lighting improve visibility without modifying geometry coordinates.

## Measurements

Select the asset, sensor and sample window. Charts use stored values/units and show invalid readings as gaps rather than interpolation. Source acquisition and edge receipt times are distinct. Operating-reference/residual rows come from unchanged existing analytics. Only configured engineering limits are drawn, labeled illustrative in simulation. The display is not a safety instrument.

## Inspections

LiDAR results include registration/asset coverage, estimated displacement, uncertainty, reinspection status and localized_relative interpretation. Missing/degraded L2 support remains inconclusive. Thermal views use actual quantitative arrays and valid/saturation masks; dark pixels are invalid and magenta pixels saturated. Image-only regions are not placed as precise 3D hotspots.

## Advisories and evidence

Filter by asset/severity, inspect lifecycle, policy, source IDs and decision trace. Current and historical support are different. An operator can acknowledge review; viewer attempts are rejected by the backend. Acknowledgment is not recovery or repair. The backend persists actor/action/rationale/audit and stable identity, so retries cannot duplicate the review effect. No process-control buttons exist.

## Monitoring

Availability shows recent receipt/validity, source clocks/basis, calibration, data quality, channel mapping, missing requirements, geometric inconclusiveness and job backlog. A connected platform with disconnected sources is degraded monitoring, not healthy equipment. SSE resumes with its durable sequence cursor after interruption. Historical queries use REST and pagination; the browser does not transfer full event history every second.

See the actual Chromium screenshots and executed checks linked from PHASE5_VALIDATION.md. Headless screenshots use software WebGL on the tested workstation; they are not GPU/field performance claims.

Select an inspection from stored history to inspect its current frame, actual geometric regions and measured thermal residual boxes. White thermal boxes are image coordinates only. Live invalidations coalesce to at most one refresh per second; overview conditions and active-event counts share a backend SQL snapshot. Historical event queries are bounded and separate from current overview updates.

## Inspection Planning

The Inspection Planning section loads backend priorities, recommendations and historical plans. Operators can set a view/time budget and request a plan; heavy computation runs in a separate bounded worker. Cyan markers/FOV glyphs indicate planned sensor positions/directions; red markers are rejected candidates; violet cells are predicted reference coverage; green cells are previously qualified measured coverage. These overlays are distinct from measured LiDAR/thermal observations.

Review requires an operator/admin role. Critical process context requires explicit acknowledgment before software-simulation approval. No approval authorizes a physical UAV. Completed synthetic inspection links show actual B3.1/thermal results and the prior plan they informed. Only completed linked acquisitions count as attempted views. A no_viable_viewpoint or requires_route_review result is explicit, not successful sensing.

The isolated Phase 6 validation stack uses http://localhost:18880 with deployment/edge/compose.phase6-validation.yaml; the earlier Phase 5 stack remains on 18780. Tokens remain local in .edge/secrets.json. See PHASE6_VALIDATION.md for actual screenshots and test scope.


## Interactive demonstrator update

The isolated UX release adds Simulation Lab and the light-neutral operational layout. See [Simulation Lab](SIMULATION_LAB.md), [redesign](FINAL_DASHBOARD_REDESIGN.md), and [browser walkthrough](FINAL_DEMO_WALKTHROUGH.md). Source recency, publisher activity and platform connection are distinct. Unknown and inconclusive data retain their original meaning.
