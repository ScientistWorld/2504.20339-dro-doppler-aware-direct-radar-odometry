# Evaluation Targets

## Primary: synthetic_doppler_core

Tests whether radar odometry produces accurate relative pose estimates in structured and feature-degenerate driving-like scenes.

- **Metric**: `avg_translation_error_pct` (lower is better)
- **Constraint metric**: `avg_rotation_error_deg_per_100m` (lower is better)
- **How to run**: `bash scripts/reproduce.sh`, or generate prediction JSON files and run `bash scripts/evaluate.sh <predictions...>`.

## Ablation: synthetic_doppler_ablation

Checks the same odometry setting while also tracking velocity quality for the combined direct-plus-Doppler method.

- **Metric**: `avg_translation_error_pct` (lower is better)
- **Constraint metrics**: `avg_rotation_error_deg_per_100m` and `velocity_rmse_mps` (lower is better)
- **How to run**: `bash scripts/reproduce.sh`.

## Additional Settings: synthetic_doppler_structured and synthetic_doppler_tunnel

Report the primary odometry metric separately for the two generated scenarios so future agents can see whether improvements hold in both a landmark-rich setting and a feature-degenerate tunnel-like setting.

- **Metric**: `translation_error_pct` (lower is better)
- **Constraint metric**: `rotation_error_deg_per_100m` (lower is better)
- **How to run**: `bash scripts/reproduce.sh`.
