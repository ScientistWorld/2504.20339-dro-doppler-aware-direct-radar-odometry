# Evaluation Targets

Scores come from `bash scripts/evaluate_train.sh` on the visible split and from the hidden evaluator on the held-out split. Both score every `*_predictions.json` artifact on disk. Every metric is an error: lower is better, and the lower bound is 0.

## Primary: synthetic_doppler_core

Accurate relative odometry over all sequences.

- **Metric**: `avg_translation_error_pct`
- **Constraint metrics**: `avg_rotation_error_deg_per_100m`, `endpoint_position_error_m`, `path_length_error_pct`
- **Eligibility**: a method is scored as failed, with all metrics at their ceilings, if its average translation error or its velocity RMSE is not better than fixed-velocity dead reckoning, if its reported velocities do not describe its own poses (RMS gap above 0.5 m/s in any sequence), or if it breaks the output contract (see `briefing/evaluation.md`).

## Constraint: synthetic_doppler_structured

Accuracy on landmark-rich scenes must not be sacrificed.

- **Metric**: `translation_error_pct`
- **Constraint metrics**: `rotation_error_deg_per_100m`, `endpoint_position_error_m`, `path_length_error_pct`

## Constraint: synthetic_doppler_tunnel

Usable odometry in geometrically degenerate scenes.

- **Metric**: `translation_error_pct`
- **Constraint metrics**: `rotation_error_deg_per_100m`, `endpoint_position_error_m`, `path_length_error_pct`

## Ablation: synthetic_doppler_ablation

Pose accuracy together with physically consistent velocity estimates.

- **Metric**: `avg_translation_error_pct`
- **Constraint metrics**: `velocity_rmse_mps`, `avg_rotation_error_deg_per_100m`, `endpoint_position_error_m`, `path_length_error_pct`

How to run: `bash scripts/reproduce.sh`, or write your own artifacts and then run `bash scripts/evaluate_train.sh`.
