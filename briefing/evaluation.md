# Evaluation Protocol

The evaluator computes relative odometry errors from prediction artifacts. For each sequence, it compares estimated and ground-truth trajectory segments and reports:

- Relative translation error as a percentage of segment length.
- Relative heading error in degrees per 100 m.
- Velocity RMSE in m/s for ablation-style checks.

The paper reports KITTI relative translation and rotation errors for automotive datasets, and relative position error for off-road data. This workspace uses the same style of relative trajectory scoring on a local synthetic FMCW radar benchmark because the full Doppler-enabled dataset used for the central claim is not publicly available.

Run `bash scripts/evaluate.sh` after generating predictions. It writes `scoring/scores.json`.
