# Experiments

All four scored experiments use the same prediction artifacts. The held-out score covers twelve sequences (six landmark-rich, six tunnel), each 72 radar scans long (18 s). Every vehicle starts at rest, then drives with speed, curvature and side slip that vary smoothly and randomly. Fixed comparator rows (fixed-velocity gyro dead reckoning and two reference variants) are reported next to each submitted method for context.

A submission only counts if it is a usable odometry output: it must beat fixed-velocity dead reckoning on both average translation error and velocity RMSE, its reported velocities must describe its own poses, and it must respect the output contract (origin start, physically possible motion). Otherwise every metric is set to its worst value.

## synthetic_doppler_core

Overall odometry quality across all held-out sequences. It establishes whether a system estimates accurate relative motion from the radar and gyroscope stream: relative translation (primary) and heading accuracy. It also checks two global consistency measures, final-position drift and travelled-distance mismatch, which a locally plausible but globally inconsistent trajectory would fail.

## synthetic_doppler_structured

The same measures on the landmark-rich sequences only. Here the scene geometry strongly constrains motion; the experiment checks that a method exploits it and stays accurate.

## synthetic_doppler_tunnel

The same measures on the tunnel sequences only. These scenes are long, smooth parallel walls with no visible ends, so the geometry barely constrains along-track motion. The experiment checks that a method still gives usable odometry when scene structure is degenerate.

## synthetic_doppler_ablation

Aggregate pose metrics plus the error of the reported per-scan body-frame velocity. It establishes whether the method's velocity estimates are physically right, not just its integrated poses. Velocity is also an eligibility condition, so poor velocities cannot be traded for pose accuracy.
