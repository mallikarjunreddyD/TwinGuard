# Utility and optimization

For a candidate, C is its usable reference-cell set, H the already qualified plus provisionally selected-cell union, A the target asset modeled area, and g=area(C−H)/A. Priority r and deficiency d are normalized engineering proxies. Suitability q is incidence×max(0,1−sampling_spacing/0.24 m). Cost c=min(1,(segment travel seconds+acquisition seconds)/request budget seconds). Redundancy z=1−|C−H|/max(1,|C|).

U = 0.25g + 0.25gd + 0.20gr + 0.15gq − 0.10c − 0.05z.

All terms and weights are stored. Score lies in [−1,1]; it is not Bayesian entropy reduction. Hard constraints are applied first. P3 selects the largest positive marginal score, updates H and location, then recomputes all remaining gains/costs. Stable viewpoint ID breaks ties. It stops when no positive feasible gain remains, budget is exhausted, or maximum views is reached. Per-asset count, previously attempted views, travel limit and return cost are enforced.

P0 uses the fixed deterministic candidate-ID schedule. P1 maximizes marginal area. P2 prioritizes the current severity/criticality terms and chooses by the same stable candidate rule. P0/P1/P2/P3 share the identical candidate pool, measurement qualification and budgets. A lower-risk asset without calibration cannot be made feasible merely to create a favorable comparison. An exhaustive reference enumerates ≤8 feasible candidates and ≤3 views for maximum area under identical route/time constraints. Its objective is explicitly coverage, not the P3 weighted utility; corresponding gaps are labeled.
