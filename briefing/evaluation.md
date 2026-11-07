# Evaluation Protocol

`bash scripts/evaluate_train.sh` scores every `*_predictions.json` artifact on disk against the labelled training sequences and writes `scoring/scores_train.json`. `bash scripts/evaluate.sh` does the same and writes `scoring/scores.json`. A held-out evaluator uses the same rules and the same artifact format, but scores the `test_*` sequences against labels that are not in this workspace.

For every sequence, the evaluator recomputes all numbers from the submitted trajectory rows alone:

- **Relative translation error (%)**: KITTI-style. Segments of 20, 35 and 50 m of ground-truth travel start every second scan. For each segment it takes the displacement between the segment's end and start, expressed in the start frame. The error is the difference between estimated and true displacement, divided by the segment length.
- **Relative rotation error (deg/100 m)**: the heading-change error over the same segments.
- **Endpoint position error (m)**: the error of the final position, expressed in the first-pose frame.
- **Path-length error (%)**: the mismatch of total travelled distance.
- **Velocity RMSE (m/s)**: the vector error of the reported body-frame velocity for each scan.

Each value is averaged over the sequences of a group (all sequences, landmark-rich only, tunnel only).

## Comparator rows

The rows `fixed_velocity_gyro` (constant 4.5 m/s forward speed with raw gyro integration), `dro_d` and `dro_g` are fixed reference comparators. The evaluator reads them from its own frozen files, so a submission cannot change them.

## Failure rules

A method is scored as **failed**, with every metric set to its ceiling, if any of the following holds:

- the artifact is not valid JSON;
- a sequence of the split is missing;
- a row count differs from the scan count;
- a row is not six numbers;
- a value is non-finite;
- a timestamp is off the scan start time by more than 1 ms;
- a position or speed is physically impossible;
- two artifacts claim the same method name;
- its average translation error is not better than the fixed-velocity dead-reckoning comparator.

The ceilings are translation 100 %, rotation 100 deg/100 m, velocity 10 m/s, endpoint 100 m, path length 100 %. Valid values are also capped at these ceilings. On the held-out split, a method is also marked failed if the test input file has been modified or removed.

The paper reports KITTI relative translation and rotation errors on real automotive datasets. This workspace applies the same style of relative trajectory scoring to a procedurally rendered spinning-radar benchmark, because the Doppler-enabled dataset behind the paper's central claim is not public.
