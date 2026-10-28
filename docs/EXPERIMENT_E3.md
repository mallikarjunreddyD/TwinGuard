# Experiment E3

E3 has separate controlled policy-semantic (E3-A) and actual upstream-analytics (E3-B) tracks. F0 and F1 receive identical normalized evidence streams; no evaluator labels enter inference. Both produce sealed public predictions before the restricted evaluator reads labels. Method behavior, policy/model/source hashes and event matching are fixed before final seeds.

E3-A executes all 22 requested controlled cases with 30 reproducible independently seeded delivery variants each (6100–6129): 660 logical scenarios. It tests single critical escalation, scopes, coincidence, invalidity, duplicate/dependent data, conflicts, recovery, acknowledgment and missing monitoring. These designed semantics repetitions are not physical fault-detection experiments or population safety validation.

E3-B uses 30 fresh seeds (7100–7129) for each of 15 conditions: healthy, normal load transition, localized geometry, hotspot, noncritical pressure anomaly, critical pressure, critical temperature, geometry-only delivery, critical pressure without UAV, stale actual prior inspection, L2 geometry, missing pressure with duplicate delivery, image-only context, critical pressure outside operating calibration, and spatially incompatible/missing critical-channel evidence. These 450 cases run the unchanged Phase 2 sensors and Phase 3/3.1 analytics on actual generated public observations. Frozen healthy models are versioned under configs/fusion/calibration. A real historical public inspection is versioned under configs/fusion/history; it is not a retimed current scan.

The existing 200 kPa process anomaly is noncritical under the example policy. A separately declared severe synthetic 500 kPa scenario crosses the illustrative pressure limit; a 70 degC synthetic process change crosses the illustrative temperature limit. New physical scenarios are explicit, not modifications of detector/noise behavior. The spatial mismatch scenario has a real geometric change and process-temperature anomaly, but only an unrelated installed pipe thermometer and pressure channel are delivered; the missing relevant critical channel must remain a critical miss, not be replaced by unrelated corroboration.

Fusion is assessed every five simulated seconds through 125 s. Source observations retain original acquisition/receipt times. Availability uses declared simulated processing assumptions; escalation delay includes this assessment cadence and is not measured transport/service response. Positive matching uses the principal asset BW-01, or inspection-context for image-only thermal findings, from fault onset through the horizon. Critical events require red. Geometric matches additionally require qualified supporting regions within the private true footprint. Unrelated warnings cannot conceal an upstream miss. Only the evaluator performs these comparisons after sealing. Secondary/nonprincipal asset events are retained but are not fully physically annotated by this principal-event benchmark.

False advisories on negative scenarios, wrong-condition advisories on positive scenarios, strict severity-qualified precision/recall, missed critical events, unknown/inconclusive outcomes and qualified-coverage failures are separate. Monitoring-loss notices are not physical-fault false alarms. The original frozen unsupported-green metric checks declared missing requirements; a supplementary audit separately counts green on scopes with no configured green requirements. Historical event support is not treated as current corroboration. Recovery timing reports the interval from the first qualified recovery observation to clearing; events unresolved at the horizon are censored, not fabricated successful recoveries.

```bash
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
twinguard fusion validate-policy --policy configs/fusion/hazards.yaml
twinguard experiment run E3 --config experiments/E3.yaml --smoke --output-dir experiments/outputs/my-E3-smoke
twinguard experiment run E3 --config experiments/E3.yaml --output-dir experiments/outputs/my-E3
twinguard experiment report --run-dir experiments/outputs/my-E3
```

--smoke uses separate development seeds 5900/6900, never the final evaluation seeds. Prior development runs and their invalid initial policy results remain in ignored phase4-* output directories. Large per-case traces/clouds are ignored by Git; compact measured results, audit/CSV data and seven figures are retained in docs/phase4. No tuning is permitted on held-out outcomes; no physical boiler safety claim is made.
