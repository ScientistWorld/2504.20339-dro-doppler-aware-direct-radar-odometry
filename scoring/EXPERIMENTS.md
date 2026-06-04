# Experiments

## synthetic_doppler_core

Compares a simple gyro-aided baseline with DRO variants on two generated driving-like radar sequences. The experiment is meant to establish whether dense radar registration and Doppler information improve relative odometry accuracy while maintaining heading accuracy on the replacement benchmark.

## synthetic_doppler_structured

Reports the same odometry metrics on the landmark-rich generated sequence alone. This checks whether a method works when the scene has enough geometric structure for scan matching to be informative.

## synthetic_doppler_tunnel

Reports the same odometry metrics on the tunnel-like generated sequence alone. This checks whether a method remains useful when geometric structure is weaker and velocity information matters more.

## synthetic_doppler_ablation

Reports the combined DRO variant with an additional velocity error metric. This gives future agents a target that captures both pose quality and the velocity-estimation side of the Doppler-aware claim.
