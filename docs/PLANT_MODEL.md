# Plant model

configs/plant.yaml is validated by PlantConfig; AssetSpec supplies stable ID, primitive kind, dimensions in metres, local origin, parent, material, expansion axis/coefficient and inspectable-region IDs. Defaults are an illustrative scaled mock-up, not commercial boiler design specifications. Dimensions, tube spacing, axial/radial segmentation, poses and material parameters are configurable.

| Asset | Geometry and placement |
|---|---|
| BW-01 | 1.8 m wide × 2.4 m high panel, 0.04 m backing, thirteen 0.045 m-radius tubes, local Z vertical; world base Z=0.35 m |
| DR-01 | Horizontal X-axis cylinder, length 2.1 m, radius 0.32 m, world centre Z=3.05 m |
| SP-01 | Right-hand connected steam line; bends represented by joined closed cylindrical segments |
| SP-02 | Left-hand return line connecting the wall assembly and drum |
| SUP-01 | Two upright rectangular posts and a horizontal beam behind the boiler |
| VL-01 | Simplified valve body, stem and handwheel; child of SP-01 |
| REF-01 | Separate fixed frame at X=2.6 m, Y=-1 m for future registration |

Tube centres span the panel width, so the complete water-wall bounds extend another tube radius at each side (1.89 m total). Panel faces use a 60×80 grid by default; tubes have 80 axial intervals and 16 radial sections. The default central bulge is sampled exactly at X=0, Z=1.2 m. Tests verify 10–50 mm peaks to 1e-10 m, a numerical implementation tolerance rather than a sensing resolution claim.

Meshes concatenate individually closed primitive surfaces. Joints overlap instead of using CAD Boolean unions; this creates internal overlapping surfaces. No mechanical volume, stress, watertight union, insulation or occlusion fidelity is claimed. Primitive components avoid degenerate triangles and have finite vertices with valid triangle indices. Surface inspection currently means all mesh triangles; region IDs attach explicit local-space fault fields.

Coordinates follow the right-handed local ENU-like world, not georeferencing. T_target_source maps column vectors from source to target. Asset records store relative poses; world poses compose the hierarchy. VL-01 follows SP-01's rigid transform. Expansion changes local geometry about local coordinate zero; no mechanical movement of attached pipes is inferred from a support shift.

`create_baseline_plant(config, seed)` returns an accepted baseline. Configuration, asset records, poses and mesh access use defensive copies. Fault simulation always starts from that baseline, never the last snapshot. Deterministic geometry is seed independent; seeds affect only explicitly enabled operating variation.

Baseline GLB nodes preserve local geometry and world placement. Baseline PLY files contain world vertices, with JSON records retaining relative asset poses. Current-state PLY and GLB geometry are baked into world coordinates; current GLB nodes are identity transforms with stable asset names. Never reapply T_world_asset to an already-world PLY. PLY/GLB vertices are float32 on disk; default reload tests allow 2e-7 m absolute error. Vertex temperatures are stored in fields.npz under {asset_id}_temperature_c, aligned with that asset's exported vertex ordering.

The Phase 0 `wall-01` catalog entry remains a deprecated alias for BW-01 so old fixtures still validate. It does not add an eighth physical asset. S0–S5 now list the seven canonical IDs, use version v2, and reference the migrated sensor/fault catalogs. The build command exports a standalone metadata/model directory; simulation exports full replay metadata.
