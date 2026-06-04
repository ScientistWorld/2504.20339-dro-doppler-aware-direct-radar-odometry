# Problem Definition

Estimate the SE(2) trajectory of a vehicle carrying a 360-degree spinning FMCW radar and a yaw-axis gyroscope. Each radar scan is a polar intensity image: rows are azimuth beams collected at different timestamps during the scan, and columns are range bins.

The benchmark input is a sequence of radar scans, beam azimuths, beam timestamps, chirp directions, range bins, and yaw rates. The output is one pose per scan, represented by timestamp, x, y, heading, and estimated body-frame velocity.

Success is measured by odometry accuracy against ground truth trajectories. The evaluation code is method-agnostic and reads prediction JSON files; it does not import the reproduced method.
