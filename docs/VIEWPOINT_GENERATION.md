# Viewpoint generation

The accepted GLB SHA256 is pinned in planner.yaml. Mesh graph transforms are applied into right-handed plant-01 world meters. Candidate centers derive from accepted asset surface bounds; positions sweep configured 2.5/3.4 m shells, azimuths −0.35/0/+0.35 rad, and height offsets −0.3/0/+0.3 m. This produces 18 positions per modality per asset, 252 candidates for seven assets. IDs hash the accepted map, asset, modality, planned transform and complete sensor configuration. No injected region or future scan selects a candidate.

Sensor +X points at the accepted asset center, +Y is left and +Z completes a proper right-handed rotation. This matches the existing Phase 2 LiDAR and pinhole camera. Sensor-local→world Transform is validated orthonormal with determinant +1. L1 LiDAR uses the unchanged 16 channels, 720 horizontal samples, horizontal FOV 1.4 rad and vertical span −0.4 to +0.4 rad. Thermal uses its own 128×96 pixels and 1.1×0.85 rad FOV.

A shell offset is not a safety certificate. Every position is separately tested against allowed volume, altitude, stand-off, no-go and measurement support. Current surfaces, dynamic obstacles, rotors and aerodynamic effects are unmodeled. Physical operation requires independent mapping and site review.
