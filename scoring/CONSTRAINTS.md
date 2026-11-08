# Constraints

Hold these fixed:

- **Data**: `data/train.npz` (labelled) and `data/test_inputs.npz` (held-out inputs). Do not regenerate, edit or replace them. The held-out evaluator verifies a digest of the test inputs and fails every method if they changed.
- **Sensor suite**: estimate motion only from the provided radar scans, timing metadata, chirp signs, range/azimuth grid, sensor constants (including the radar's offset ahead of the rear axle), and gyro samples.
- **Output contract**: one `*_predictions.json` per method under `checkpoints/`, `method/` or `baseline/`. It must contain every sequence and exactly one finite row `[t, x, y, heading, vx_body, vy_body]` per scan, with `t` equal to the scan start time and the first pose at the origin with heading 0. Each row's body-frame velocity must describe the motion to the next row's pose (RMS gap at most 0.5 m/s per sequence), and motion between scans must be physically possible. Use a unique method name. `fixed_velocity_gyro`, `dead_reckoning`, `dro_d` and `dro_g` are reserved comparator rows owned by the evaluator.
- **Evaluation**: `eval/` and `scripts/evaluate*.sh` read artifacts only. They must not import from `method/` or produce predictions.
- **Dependencies**: `environment/container.def` and `environment/setup.sh`.

Invalid shortcuts:

- using labels at inference time on sequences being scored;
- fitting a predictor that memorizes training trajectories;
- recovering hidden trajectories from the generator instead of from the radar, including fitting the generator's motion or scene model, or rendering it, to the held-out inputs;
- external localization;
- writing scores, flags or ground truth into artifacts;
- editing comparator files, data files or evaluators;
- reporting paper numbers instead of computed scores.

Hyperparameters may be tuned on the training split only.
