# Experiments

## automotive_doppler_main

Compares a simple gyro-aided baseline with DRO variants on two driving-like radar sequences. The experiment is meant to establish whether dense radar registration and Doppler information improve relative odometry accuracy while maintaining heading accuracy.

## automotive_ablation

Reports the combined DRO variant with an additional velocity error metric. This gives future agents a target that captures both pose quality and the velocity-estimation side of the Doppler-aware claim.
