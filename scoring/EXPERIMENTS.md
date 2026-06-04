# Experiments

## synthetic_doppler_core

Compares odometry predictions on two generated driving-like radar sequences. The experiment is meant to establish whether the proposed odometry family improves relative pose accuracy while maintaining heading accuracy on the replacement benchmark.

## synthetic_doppler_structured

Reports the same odometry metrics on the landmark-rich generated sequence alone. This checks whether a method works when the scene has enough geometric structure for scan matching to be informative.

## synthetic_doppler_tunnel

Reports the same odometry metrics on the tunnel-like generated sequence alone. This checks whether a method remains useful when geometric structure is weaker and velocity information matters more.

## synthetic_doppler_ablation

Reports the same aggregate odometry setting with an additional velocity error metric. This gives future agents a target that captures both pose quality and velocity-estimation quality.
