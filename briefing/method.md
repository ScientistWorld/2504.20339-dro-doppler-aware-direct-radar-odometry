# Method Summary

DRO estimates radar odometry by directly registering dense radar intensity scans rather than extracting feature points. For each incoming scan, it optimizes a locally continuous SE(2) trajectory over the scan duration.

The implemented reproduction includes the paper's core computational steps:

- Constant body-frame velocity motion model with gyroscope-provided yaw integration.
- Doppler range correction proportional to radial velocity and chirp direction.
- Direct scan-to-local-map intensity cross-correlation.
- Alternating up/down chirp split with local infill to construct matched Doppler images.
- Doppler velocity objective that maximizes cross-correlation after radial range shifting.
- Online Cartesian local-map update with a low-pass filter.

The authors' public release is included under `method/upstream_dro/` for reference. The runnable benchmark implementation is `method/dro_synthetic.py`.
