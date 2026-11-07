# Method Summary

DRO estimates radar odometry by directly registering dense radar intensity scans instead of extracting feature points. For each incoming scan, it estimates a locally continuous SE(2) trajectory over the scan's duration. The trajectory starts at the pose estimated for the end of the previous scan.

The reproduction (`method/dro_synthetic.py`) implements the paper's computational steps:

- Constant body-frame velocity during a scan; orientation from gyroscope integration.
- Gyro bias from the paper's stationary-vehicle heuristic: average the raw gyro rate over the first stationary scans (estimated speed below 5 cm/s), then low-pass update it whenever the vehicle is stationary again. The running mean is applied while the first samples accumulate.
- Doppler range correction proportional to radial velocity and chirp direction.
- Direct scan-to-local-map intensity cross-correlation (`O_psi`) on a Cartesian local map updated with a low-pass filter (gamma = 0.1).
- Up/down chirp split with local Gaussian-process infill, giving a matched pair of Doppler images.
- Doppler velocity objective (`O_d`): cross-correlation of the two images after radial range shifting.
- Normalized gradient ascent with step halving, after a coarse grid initialization.

The three variants follow Table I: `dro_d` (O_d only), `dro_g` (O_psi only) and `dro_gd` (both). In `dro_gd`, the Doppler-only estimate initializes and weakly anchors the combined objective. The relative weight of O_psi is selected on the training split by `method/tune_gd_weight.py` and stored in `method/dro_config.json`.

The authors' public release is included under `method/upstream_dro/` for reference.

Pipeline:

- `bash scripts/method.sh` writes the `dro_gd` artifact.
- `bash scripts/ablations.sh` and `bash scripts/baseline.sh` regenerate the comparator outputs under `checkpoints/comparators/`.
