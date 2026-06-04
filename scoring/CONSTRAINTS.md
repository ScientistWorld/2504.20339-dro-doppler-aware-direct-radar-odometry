# Constraints

Future improvements must use the same generated radar sequences and prediction format unless explicitly adding a new experiment. Evaluation must read artifacts and must not call into `method/`.

Valid changes include improving direct intensity registration, Doppler infill, optimization, robust weighting, local-map update, and motion modeling within the radar odometry setting.

Invalid shortcuts include using ground-truth poses or velocities at inference time, changing the generated test trajectories to easier cases, replacing odometry with supervised fitting to the ground truth, or reporting paper numbers instead of computed scores.
