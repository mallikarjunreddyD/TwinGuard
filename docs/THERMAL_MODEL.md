# Virtual radiometric camera

A pinhole camera defaults to 128×96 pixels, horizontal/vertical FoV 1.1/0.85 rad, near/far radial ranges 0.1/20 m. The camera uses the same right-handed +X-forward, +Y-left, +Z-up body frame as LiDAR. fx=w/(2 tan(hFoV/2)), fy=h/(2 tan(vFoV/2)), cx=(w-1)/2, cy=(h-1)/2. Pixel centres are integer (column,row); the normalized ray is proportional to (1,-(column-cx)/fx,-(row-cy)/fy). These formulas and the exported intrinsics permit conversion to a conventional +Z-forward camera when needed.

Every pixel independently intersects the actual current plant with the first-hit raycaster. The selected asset/triangle is tracked privately. Temperature at the hit is the barycentric weighted sum of that triangle's three physical vertex temperatures. This keeps gradients/hotspots aligned with geometry and guarantees opaque front geometry hides rear temperatures. Tests cover a known-temperature triangle, a gradient, uniform planes, an occluded hot surface, actual S3 projected hotspots, viewpoint changes, invalid pixels and saturation.

The grey-body surrogate is T_app,K^4 = epsilon T_surface,K^4 + (1-epsilon) T_reflected,K^4. Celsius values are converted to Kelvin before exponentiation, then converted back. Default epsilon=0.95 and reflected temperature=25 degC; L0 uses epsilon=1. Gaussian instrument noise, bias, optional quantization/outliers and random invalid pixels are then applied. Saturation clips the instrument value to configured Celsius limits and reports a legitimate saturated-pixel count. No intersection/out-of-range/invalid pixels are NaN with valid_mask=false, never a synthetic zero-temperature background.

The numeric temperature_c array and boolean valid_mask in NPZ are the measurement. NPY is a numeric companion; false-color PNG is presentation only, with a color scale in degC. Public metadata includes intrinsics, reported extrinsics, configuration/calibration reference, emissivity/reflected-temperature assumptions and instrument quality counts. It contains no source mesh, triangle IDs, actual surface temperatures or true pose. Separate private arrays store the reference surface and apparent temperatures for verification.

Apparent-model RMSE measures stochastic instrument effects relative to this assumed radiometric equation. The separate difference from physical surface temperature includes emissivity/reflection effects and can be much larger; neither is physical camera calibration. The report exposes both, avoiding a claim of commercial ±2 degC performance. No independent random hotspot or anomaly overlay is generated.

Limitations: no wavelength-specific spectral response, distance-dependent atmospheric attenuation, humidity, specular multi-bounce reflection, exposure integration, lens blur/distortion, emissivity maps, camera self-heating or validated calibration. Surface fields are the Phase 1 vertex approximation; local hotspots do not trigger a solved thermal/mechanical feedback. Camera acquisition is instantaneous. Noise/pose settings are assumed and require physical validation before industrial accuracy claims.


## Phase 3 update

Phase 3 correction: valid_mask now means available measured pixels, including clipped values. Public saturation_mask and pixel_status identify clipping separately. Quantitative analytics uses status 1 and excludes status 3 saturation. Legacy captures without explicit saturation arrays are conservatively inconclusive; see OPERATING_ANALYTICS.md.
