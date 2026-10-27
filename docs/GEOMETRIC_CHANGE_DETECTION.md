# Geometric change detection

Both detectors consume public measured clouds and their estimated registration. B1/B2 use a fixed nearest-neighbor threshold (25 mm). B3 constructs baseline patches across the entire accepted wall and measured support surfaces; no evaluator ROI is supplied. Default patch radius is 180 mm and spacing 120 mm. PCA estimates normals, rejects line-like neighborhoods, multiple depth layers and excessive roughness, then orients the wall normal against the fixed +Y reference or uses the baseline viewing direction on other assets. Unreliable orientation yields a qualified estimate, never an invented sign.

Independent spatial occupancy cells establish common coverage before comparing normal-projected medians. Each side requires at least eight samples, at least three common cells and 25% common-cell support. Nearest-neighbor distances are retained as a simple baseline. Patch uncertainty is the maximum of robust local dispersion, the healthy empirical floor and registration quality; it is not divided by sqrt(N), since points share pose and surface errors.

The B3 engineering screen is **abs(displacement) - 1.5 * uncertainty_score > 5 mm**. The multiplier is not a 95% confidence statement. A fixed healthy-only calibration estimates a conservative 90th-percentile residual floor from independent seeds 50–54; thresholds remain unchanged on held-out faults. The report separately evaluates empirical engineering-score coverage. A high coverage value can reflect conservatism and low sensitivity.

Significant adjacent patches form connected regions with world bounds, representative displacement, uncertainty and approximate area. Unique intersection with fixed accepted asset volumes permits an asset ID and compatible GeometricDetection; ambiguous association retains asset_id=None. Thermal association remains image-only. Public inspection target IDs never become perfect point/pixel segmentation.

Absent returns, unstable registration, sparse common coverage and unseen assets produce insufficient_coverage/inconclusive outputs with null estimates. GeometryResult.asset_statuses prevents an observed wall from implying an unseen support is healthy. Empty regions mean no qualified detected change; they do not establish plant health. Registered clouds are artifacts for review even when their registration is qualified as inconclusive.

Observed limits: B3 detected none of the 10/20 mm held-out cases, about one third of 30 mm cases and two thirds of 50 mm cases. Registration bias, partial coverage and smoothing of compact deformations limit sensitivity. Estimates are normal displacement, not full deformation vectors or a physical metrology claim. Read PHASE3_VALIDATION.md before using these outputs.


## Phase 3.1 update

The original B3 implementation remains unchanged. Explicit --methods B1 B2 B3 B3.1 selects comparisons; B3.1 requires --improved-calibration. Its 80/120 mm supported patches use robust wall-relative residual correction, per-location healthy bias/envelopes and a calibrated neighboring-pair screen. All B3.1 estimates carry measurement_basis=localized_relative; broad/uniform wall motion can be removed and is outside this method’s capability. Raw estimates, removed common-mode component, scale, calibration support, margin, coverage and reinspection_candidate are explicit. Sparse/uncalibrated evidence remains inconclusive. See PHASE3_1_IMPROVEMENTS.md for the mathematics and PHASE3_1_VALIDATION.md for independent results.
