# Assumptions and limitations

No plant geometry, calibrated thermal/mechanical model, sensing equipment, measured uncertainty, site safe limits or validated industrial trials have been supplied. Geometry references point to future artifacts; Phase 0 checks metadata rather than implementing geometry. Example operating/fault values illustrate configurations only. Boiler response depends on installation, material, mounting, load history and environment; no universal safe envelope is assumed.

Synthetic data do not independently establish real-world detection accuracy. The current observations are hand-authored synthetic schema fixtures. A seed and configuration support reproducible future execution but do not establish simulator fidelity. Dataset manifests marked pending are templates, not downloaded or validated sources.

Uncertainty is currently scalar and nonnegative; distributions, correlations, calibration, registration covariance and propagated uncertainty need scientific design. Confidence fields do not by themselves establish probabilistic reliability. Time ordering assumes a shared UTC domain; clock drift, missingness, duplicate identity resolution, delayed arrival and freshness policy require later integration/fusion work.

Ground-truth separation is enforced in model acceptance, public serialization and separate filesystem paths. It is not an OS security boundary against code running as the same user, arbitrary strings covertly carrying labels, or an engineer bypassing these interfaces. Use separate runtime identities/mounts for stronger isolation. No authentication, storage backend, network ingestion or safety-control actuator is implemented. The metadata API is intended for local development.

Developer review decisions: confirm the Phase 1 plant geometry/material model and catalog; choose site-specific sensor/calibration configuration; approve unit/covariance extensions and version migrations; select licensed public datasets and held-out evaluation design; specify uncertainty/confidence methodology; define real clock-skew handling and future storage/access controls. No approval is needed to execute this infrastructure; these decisions gate later engineering claims.

Open3D, OpenCV, React, UAV simulation, MQTT/OPC UA, databases, GPU services and all Phase 1–7 algorithms are deliberately pending. Docker execution depends on an accessible daemon; exact verification outcomes are recorded separately.
