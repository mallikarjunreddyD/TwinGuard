# Registration

Phase 3 implements CPU Open3D point-to-point ICP and multiscale point-to-plane ICP with Tukey robust loss. B1 is reported-pose alignment only; B2 is conventional ICP plus nearest-neighbor screening; B3 is robust ICP plus patch screening. B1 is an intentionally weak reference, not an independent measurement of sensor accuracy.

NPZ/PLY input must resolve to a validated public capture: finite measured sensor-local points, stated units, frame, reported pose and uncertainty. Preprocessing retains original and processed points, rejects invalid/range failures, optionally removes statistical outliers and voxel downsamples. No synthetic correspondence IDs are used. Public target IDs identify intended inspection targets, not segmentation labels.

With reported sensor-to-world matrices Wb and Wc, ICP estimates world correction C from measured correspondences. The reported transform is **T_baseline_current = inv(Wb) C Wc**. Registered export coordinates are **C Wc p_current**, in the baseline world frame. This distinction matters when applying the saved transform to raw sensor coordinates. Both the convention and export frame are persisted.

Stable reference selection uses only the fixed accepted as-built reference JSON. REF-01 is preferred if sufficiently sampled and observable. If its observed normals cannot constrain a rigid solution, fallback uses observed non-monitored geometry, excluding complete BW/SUP reference volumes. It never receives fault ROIs or current simulator meshes. The accepted reference was generated once from the healthy synthetic baseline; it is not independently surveyed physical geometry.

Two local starts quantify repeatability; selection uses observed fitness/RMSE only. Quality gates include correspondence count, overlap, normal-information conditioning, residual RMSE, local-start disagreement and correction versus reported pose budget. These are engineering screens. Open3D termination alone is insufficient and `converged` is qualified by these checks. A valid screen does not prove a globally correct transform: repetitive geometry and small local minima remain failure modes.

All tunables are typed in analytics/config.py and overridable in configs/analytics/default.yaml. Typical defaults: 10 mm voxel, 260 mm correspondence radius, scales 150/80/40 mm, 35 iterations/scale, 25 mm Tukey scale, 40 correspondences minimum. See PHASE3_VALIDATION.md for actual errors and failures; robust registration did not uniformly beat conventional ICP. Results include quality flags, runtime, uncertainty score, NPZ artifact/hash/frame and PLY export when nonempty. The benchmark's finalized export metadata references its existing PLYs; original sealed predictions are retained.


## Phase 3.1 update

B3.1 (algorithm v3.1) uses the same conventional point-to-point ICP transform as B2; two methods share that immutable computation in a combined invocation. D6 justified this scoped choice on diagnostic geometry, while strict REF-01-only conditioning failed all 40 trials. B3.1 retains registration gates. Its subsequent robust wall-normal offset/tilt removal is a relative measurement basis and does not improve or replace the saved six-DOF transform. Original robust registration remains selectable as B3. See PHASE3_1_ROOT_CAUSE.md and PHASE3_1_IMPROVEMENTS.md.
