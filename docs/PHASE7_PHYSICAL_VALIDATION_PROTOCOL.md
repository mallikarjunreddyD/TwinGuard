# Phase 7 physical validation protocol

Status: **BLOCKED / PENDING physical resources**. The user confirmed on 29 October 2026 (Asia/Calcutta) that no physical data or equipment is available. No surveyed physical LiDAR data, instruments, metrology certificates, thermal calibration records, environmental measurements, site certificates or commissioning authority have been supplied. The software sensor is synthetic. None of the tests below has been represented as executed. This protocol freezes proposed acceptance criteria; site engineering must approve the final scope before physical acquisition.

## Surveyed geometry and displacement

| Evidence ID | Test and independent measurement | Proposed acceptance | Current status / blocker |
|---|---|---|---|
| PHY-01 | Survey scanner, fiducials, wall target and surrounding registration features in a traceable common frame. Record serials, firmware, units, coordinate conventions and signed calibration certificates. | Expanded reference uncertainty at most 1 mm for the 10 mm target; measured reference resolution and uncertainty budget recorded. | PENDING equipment and accredited reference |
| PHY-02 | Healthy target and independently surveyed localized out-of-plane offsets **10, 20, 30 and 50 mm**. Randomize target position/extent and blind the analyst. Independent metrologist retains labels until sealed predictions. Include rigid translation/rotation controls and support movement. | Primary claim remains localized relative change. Rigid/support displacement must remain explicitly unsupported unless a separate validated method is introduced. | PENDING surveyed target |
| PHY-03 | Standoff **2, 3 and 4.5 m**, incidence **0, 30 and 60 degrees**; record actual beam footprint, returns, angular sampling and occlusion. Include at least one heldout distance and angle outside empirical support. | Unsupported domains abstain. Qualified groups report bias, MAE, RMSE, repeatability, common coverage, registration failures and localized recall; never equate ICP fitness with survey accuracy. | PENDING instrument |
| PHY-04 | At least 30 independent healthy and 30 independent fault trials per primary claim group; independent fit, screen and final test sessions/days. Repeat each surveyed target placement at least 10 times. | Proposed localized recall lower 95% binomial bound >=0.80, healthy false-positive upper bound <=0.10; report actual interval width and abstention rate. Increase sample count when bounds cannot support the claim. Predeclare a maximum 20% abstention for each supported primary group. | PENDING blinded protocol approval |
| PHY-05 | Register repeated scans against surveyed fixed fiducials, with independent checks withheld from the registration fit. Include smooth planar and well-conditioned surroundings. | Proposed normal displacement bias <=2 mm and 95th percentile absolute error <=5 mm for a 10 mm quantitative claim. Failure narrows the supported claim; thresholds may not be retuned on final trials. | PENDING metrology |
| PHY-06 | Dry/wet surface, emissivity/reflectivity variation, ambient illumination, vibration and temperature conditions with measured values. Include explicit occluders independent of the defect. | State qualified envelope separately for every tested condition; outside-envelope cases unknown/inconclusive. No extrapolation from synthetic noise levels to physical tolerances. | PENDING environmental facility |

Do not use target labels, true scanner poses or heldout survey control points as production inference inputs. Archive raw instrument exports, measured reported poses, clock records, transform chains, immutable model/configuration hashes, signed survey records, sealed predictions and restricted evaluation labels separately. For every error statistic report the metrology uncertainty, number of independent sessions and cluster confidence interval. A new correction after final testing requires new untouched physical samples.

## Thermal calibration and association

| Evidence ID | Test | Proposed acceptance | Current status |
|---|---|---|---|
| PHY-07 | Traceable blackbody at at least three temperatures spanning the intended approved operating range; repeated measurements at each standoff/angle; measured emissivity, reflected apparent temperature, ambient conditions and instrument drift. | Agreement with the declared manufacturer/calibration uncertainty plus measured reference uncertainty; numerical tolerance must be approved from the actual instrument certificate. No invented temperature accuracy. | PENDING camera and blackbody |
| PHY-08 | Survey visible and hidden thermal targets; validate image-only association separately from extrinsic 3D localization. Blind the evaluator to hotspot location. | Image-only output must not claim a 3D hotspot. A 3D claim requires independent surveyed extrinsics, association-error distribution and preapproved spatial tolerance. | PENDING extrinsic calibration |
| PHY-09 | Timestamp synchronization, drift and discontinuities under loss/reconnection; independently record wall time. | Verified source-clock uncertainty must be included in the approved freshness budget; uncertain clocks cannot obtain authoritative critical interpretation. | PENDING clock instrumentation |

## Relevant-environment and commissioning boundary

| Evidence ID | Required test | Status |
|---|---|---|
| SITE-01 | Approved site process limits, representative operational loads, surveyed map/access rules and independent operator review. | PENDING site authority |
| SITE-02 | Site-approved CA and identities, key storage/rotation, trust-revocation tests, firewall zoning, secure read-only OPC UA, MQTT ACLs, backup owner and recovery drill. | PENDING commissioning; laboratory certificates are insufficient |
| SITE-03 | Sustained load and failure tests on intended edge hardware, representative network latency/loss, approved storage horizon and full artifact restore. | PENDING relevant environment |
| SITE-04 | Integrated reviewed inspection and measured reacquisition with human authorization. No flight/process commands are provided by this software. | PENDING physical demonstration |

Software evidence cannot close these tests. Physical readiness is **NO-GO until these prerequisites and approved acceptance criteria are met**; this is separate from a software research release decision.
