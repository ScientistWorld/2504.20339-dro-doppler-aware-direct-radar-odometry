# Research Direction

Improve radar odometry for a vehicle carrying a 360-degree spinning FMCW radar with alternating chirps and a biased yaw-rate gyroscope. The goal is accurate SE(2) poses and body-frame velocities, both in landmark-rich streets and in tunnels whose geometry barely constrains along-track motion.

In scope:

- better use of the dense radar intensity and of its chirp-dependent range structure;
- motion-distortion and timing modelling;
- velocity observability in degenerate scenes;
- gyroscope bias handling;
- vehicle kinematics (the radar's offset from the rear axle is known);
- temporal consistency and robust estimation;
- principled hyperparameter selection on the training split.

Out of scope:

- fitting or memorizing trajectories;
- exploiting knowledge of how the benchmark was generated rather than the sensor data;
- external maps or sensors;
- modifying the data, comparators or evaluators.
