# Phase 7 corrected full E4 stress

**Execution completed; critical timeliness acceptance FAILED. P5-01 remains OPEN.** Real CPU/Docker/PostgreSQL/MQTT/OPC UA/API/Chromium operation, not emulated transport latency or field hardware.

The first fresh full attempt (`phase7-V4-full-E4`) stopped at an actual queue-drain timeout after 872.4 s amid overlapping backlog streams. Its raw report and timestamp seal are retained. The fresh isolated retest (`phase7-V4-full-E4-recovery-retest`) used a declared 900 s bounded recovery observation window instead of the first controller's 240 s drain window. **No 10 s critical TTL, qualification gate or F1 rule changed.** This retest is not a latency fix or proof of critical reliability.

The retest executed **19 profiles over 1048.21 s**, including three normal streams, three pressure-critical streams before any UAV input, accelerated normal streaming, duplicates/reordering, worker/broker/API/database restart, real read-only numeric OPC UA, missing-data monitoring, LiDAR/thermal/L2 inspection and a live browser. **99 concurrent P3v2 requests** exercised the bounded planning worker. All **6204 jobs** ended completed. Per-profile completeness, API latency/statuses and samples are in the raw report and `phase7/V4-full-E4-recovery-retest-summary.json`. Transient API 502 responses occurred during intentional interruptions; do not describe uninterrupted availability.

| Critical workload | Actually published critical readings | Current | Stale | Missed among published denominator | Receipt→advisory p50 / p95 / p99 / max s |
|---|---:|---:|---:|---:|---|
| Full retest | 186 | 168 | 18 | 0 | 1.609 / 9.402 / 10.075 / 10.170 |
| Measured 500-message paused ordinary backlog, overlapping streams | 188 | 116 | 72 | 0 | 1.105 / 4.322 / 5.811 / 5.868 |

Current/stale labels come from each reading's own committed temporal decision, joined against the actually published public pressure samples and unchanged configured limit. A red latched event is not proof that every new reading was current. Receipt latency omits time spent before receipt; full acquisition-to-commit rows remain in the summary. Thus short receipt latency can coexist with stale mapped acquisitions.

Recovery stop-to-observed-ready: fast worker **8.568 s**, broker **7.069 s**, API **9.275 s**, database **10.959 s**. All previously stored event IDs survived these four checks. Exact queue/resource samples and actual browser timestamps are retained; no field-equivalent p99 assertion is made.

## Saturation and diagnosis

A separately labeled **10000 pending fixture-job fault injection** measured **10069 pending jobs** before two real authenticated MQTT publications. These fixture jobs are not 10000 fabricated sensor observations or a throughput benchmark. Both the ordinary and critical message received broker PUBACKs but were quarantined at the global durable admission limit; both are **missed at saturated admission**. Only the 10000 fixture rows were removed after testing. `phase7/queue_saturation.json` retains hashes, times and quarantine reasons. Critical worker priority cannot revive rejected messages or expired source time.

Measured constraints include serialized F1 state transitions, concurrent CPU contention, finite ingestion/worker service rate and unbounded accumulated trace histories. A longer drain deadline only permits observing recovery. The software retains and reports overload instead of weakening TTLs or asserting exactly-once delivery. A reserved, independently requalified critical admission/transport channel and representative hardware/load-envelope validation remain required work before closing P5-01.

Reproduction: deploy the explicit loopback overlays and run `scripts/phase7_e4_stress.py`, `scripts/phase7_e4_corrected.py`, `scripts/phase7_critical_boundary.py` and `scripts/phase7_queue_boundary.py` with new output paths. Do not run projects on conflicting ports. Original E4/E5 reports and seals remain unchanged.



## Final admission correction and complete retest

The deployed correction reserves100 pending slots only for authenticated authoritative critical readings that pass the original temporal qualifier. Ordinary pending limit10000; total pending bound10100. PostgreSQL admission counting is serialized across sources. Normal, unknown-quality/clock, stale and unqualified observations cannot use the reserve; worker/F1 independently requalify every admitted reading. No TTL or detector/F1 threshold changed.

Actual boundary retest: ordinary persisted0, current critical persisted1 and was assessed current; a further critical reading at the10100 pending bound persisted0. The complete fresh-database retest executed all 19 profiles over about1045s: **186/186 current**, states {'current': 186}; receipt→commit p50/p95/p99/max **0.813/5.971/6.918/7.114s**. This is a bounded laboratory pass, not a causal attribution of latency improvement to a reserve that may not be exercised below saturation. Earlier failures and differing concurrent CPU loads remain relevant.

A further actual500-message backlog/critical/planning test initially exposed reused MQTT client IDs; a second run corrected IDs but inspection messages were rejected because a truncated replay put their anchor in the future. No heavy-job concurrency was claimed from those submissions. The publisher now uses unique client IDs and waits for the actual scheduled capture anchor; server future-clock rejection remains unchanged. Fresh v3 results: **145/184 current**, states {'current': 145, 'stale': 39}; p95/p99 **11.205/12.065s**. Actual inspection/critical interval overlap is documented separately in `mixed_inspection_overlap_final.json`; nominal task submission is insufficient.

The timing decomposition found only about0.114s p95 emission-to-ingestion delay, but about10.965s p95 ingestion-to-job wait;12critical assessments actually overlap the two inspection intervals. Queue/service pressure, not packet arrival alone, explains the measured recency failure. This is a measured association and capacity boundary, not a calibrated hardware model.

Final raw output: `/mnt/d/TwinGuard/phase7-V4-full-E4-admission-retest` and `/mnt/d/TwinGuard/phase7-V4-mixed-boundary-retest-v3`. Compact summaries are under `docs/phase7`. Bounded software results improve readiness evidence; representative hardware/network rates, longer capacity behavior and site commissioning remain unvalidated. The heavy mixed workload fails the unchanged freshness acceptance. P5-01 remains OPEN, including this measured laboratory overload boundary.


## Original-rate source-delay boundary

An additional requested 1× replay on the populated laboratory instance produced 43 current and 19 stale critical readings, with two real heavy jobs and three overlapping critical assessments. All 62 readings received priority zero. Publisher schedule lag was already 10.748 seconds at p95 before emission; emission-to-ingestion p95 was 0.069 seconds and post-ingestion queue wait p95 was 0.339 seconds. Analysis and fusion/commit p95 were 0.068 and 0.231 seconds. This establishes a source/replay freshness failure, without establishing a 1 Hz server-capacity failure. The cause of the publisher's pacing delay is not uniquely attributed. Source timestamps and the 10-second TTL were retained. See [timing decomposition](phase7/nominal_boundary_analysis.json).
