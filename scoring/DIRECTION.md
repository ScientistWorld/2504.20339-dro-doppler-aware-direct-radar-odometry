# Research Direction

Work on radar odometry for a vehicle carrying a 360-degree spinning FMCW radar and yaw-rate sensor. The intended research space is estimating accurate SE(2) pose and body-frame velocity from the provided radar intensity sequences and sensor metadata.

Acceptable directions include better use of radar intensity patterns, sensor timing, range and azimuth measurement structure, yaw-rate measurements, temporal consistency, and robust handling of sparse or ambiguous scene structure.

Do not switch to unrelated localization paradigms that bypass the benchmark, such as fitting to ground-truth trajectories, using external maps or sensors, training a generic predictor only to memorize this generated benchmark, or changing the data generator/evaluator to make the task easier.
