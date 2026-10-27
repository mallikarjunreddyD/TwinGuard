# Physics surrogate

The operating model is a deterministic engineering surrogate, not a thermodynamic boiler solver, CFD or FEA. configs/plant.yaml defines load references, pressure/temperature equilibria, time constants, ambient temperature, material coefficients and optional smooth variation. configs/profiles/P0–P4.yaml provide executable steady, load increase, load decrease, startup and abnormal-process examples.

Load is linearly interpolated between scenario operating-profile points and held at endpoint values afterward. Temperature and pressure equilibria are affine functions of the same load:

x_eq(L) = x_reference + gain × (L - L_reference).

Each variable satisfies dx/dt=(x_eq-x)/tau. Within each linear-load interval the exact update is:

x(h)=e0 + b(h-tau) + (x0-e0+b*tau)exp(-h/tau).

This analytical update remains stable even when the requested output interval exceeds tau. Output times do not set the numerical accuracy; each state is recomputed from the initial state and profile breakpoints, making random-access calls independent of evaluation order. The initial state is the equilibrium for the initial load. Startup is a ramp from the configured low-load equilibrium, not a cold boiler combustion model. Defaults: L_ref=0.5, T_ref=180 degC, P_ref=800000 Pa, gains 100 degC/load and 600000 Pa/load, tau_T=25 s, tau_P=15 s, ambient 25 degC.

Optional process_variation_c adds a smooth sinusoidal temperature disturbance with a seeded phase. It defaults to zero. The RNG is reconstructed from the seed for each evaluation, so call order cannot change results. Pressure is never independently randomized. Configurations that imply negative absolute pressure or temperatures below absolute zero are rejected. Explicit process faults that create invalid physical states also fail. These are representation constraints, not safe boiler envelopes.

Normal thermal expansion is axial: delta_L=alpha×L_reference×delta_T. Each asset has its own alpha and local expansion axis. The local coordinate-zero plane anchors that axis. Water-wall Z=0 is anchored; its top moves with temperature. Supports/reference remain at ambient and use alpha=0. Other process-facing assets share the operating temperature by default. This model does not solve constrained stresses, bending, radial expansion or temperature-dependent material properties. Child rigid poses compose normally but are not remapped by a parent's deforming surface.

Localized hotspots change the surface field without a solved thermoelastic feedback. Process disturbances modify the selected process variable but do not automatically alter geometry or surface temperature. This deliberate uncoupling prevents fabricated secondary effects; adding heat-transfer/mechanical coupling requires a future validated model. Baseline/load-induced expansion and fault-induced displacement are stored separately.

S1 v2 removes Phase 0's hand-written temperature/displacement-reference hints; the load model and alpha now determine those quantities. The optional legacy hint fields remain readable as descriptive metadata, and are not alternative imposed physical boundary conditions. S5 historical inspections evaluate the initial reference plant before t=0; no prehistory dynamics are invented. The subsequent process event remains at +90 s. Evidence freshness decisions belong to Phase 4.
