# Train/Test Evaluation Design Notes

> **Superseded (hardening iteration).** The even/odd frame split described below was replaced. The visible split is now four labelled sequences in `data/train.npz`. The held-out split is six separate sequences: their inputs are in `data/test_inputs.npz`, their labels and comparator rows only in `eval/test/`. See `HARDENING.md`.

## Checks and Changes

- Checked `scripts/evaluate_train.sh` and `scripts/evaluate_test.sh` side by side. The test script calls `eval/test/evaluate.py`, writes `scoring/scores_test.json`, and uses a `test` slice marker through the evaluator metadata.
- Checked for hardcoded method defaults. Both split scripts enumerate `*_predictions.json` artifacts under `checkpoints/`, `method/`, and `baseline/` when no explicit files are passed.
- Checked for train/test cross-import leakage. The split evaluators do not import from each other.
- Fixed a label-trust shortcut: train/test evaluators no longer trust `ground_truth` embedded in method prediction artifacts. They load canonical scenario poses from `data/synthetic_dro.npz` and use artifacts only for predicted trajectories and velocities.
- Added two extra anti-shortcut metrics to both split evaluators: `endpoint_position_error_m` and `path_length_error_pct`. These triangulate the existing local segment errors with global trajectory drift and path-length consistency.
- Updated `scripts/evaluate_train.sh` and `scripts/evaluate_test.sh` to pass the canonical data path explicitly.
- Updated `scoring/reference.json` so every metric entry has `higher_is_better`, `coefficient`, and `description`. Added the new drift/path metrics to the synthetic experiments computed by the train/test evaluators.
- Confirmed `scoring/scores_train.json` and `scoring/scores_test.json` are absent.
- Ran `bash -n scripts/evaluate_train.sh` and `bash -n scripts/evaluate_test.sh`; both passed.

## Runtime Concerns for Next Iteration

- The split evaluators were not executed in this source-only pass. The runner should regenerate `scores_train.json` and `scores_test.json` and confirm the added metrics are finite for all shipped prediction artifacts.
- The legacy unsplit `scripts/evaluate.sh` still uses `eval/odometry_metrics.py`, which emits the older metric subset. That is outside this iteration's allowed edit scope, but it means `scoring/scores.json` will not contain the new split-only drift/path metrics until the unsplit evaluator is aligned or retired.
- The even/odd frame split is cheap and calibrated, but adjacent frames are still highly correlated. The added endpoint and path-length metrics make visible metric gaming harder, but a future stronger test split could add held-out generated scenarios if the platform can keep those data hidden.
- Because `data/synthetic_dro.npz` is visible in this workspace, a method that directly reads canonical poses at inference time could still cheat. That shortcut is explicitly invalid in `scoring/CONSTRAINTS.md`; the current design now at least prevents cheating by mutating labels inside prediction artifacts.
