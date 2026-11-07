# Experiments

All four scored experiments use the same prediction artifacts. The held-out score covers six sequences (three landmark-rich, three tunnel), each 72 radar scans long (18 s). Every vehicle starts at rest, then drives with time-varying speed and yaw rate. Fixed comparator rows (fixed-velocity gyro dead reckoning and two reference variants) are reported next to each submitted method for context.

## synthetic_doppler_core

Overall odometry quality across all held-out sequences. It establishes whether a system estimates accurate relative motion from the radar and gyroscope stream: relative translation (primary) and heading accuracy. It also checks two global consistency measures, final-position drift and travelled-distance mismatch, which a locally plausible but globally inconsistent trajectory would fail.

## synthetic_doppler_structured

The same measures on the landmark-rich sequences only. Here the scene geometry strongly constrains motion; the experiment checks that a method exploits it and stays accurate.

## synthetic_doppler_tunnel

The same measures on the tunnel sequences only. These scenes are long, smooth parallel walls with no visible ends, so the geometry barely constrains along-track motion. The experiment checks that a method still gives usable odometry when scene structure is degenerate.

## synthetic_doppler_ablation

Aggregate pose metrics plus the error of the reported per-scan body-frame velocity. It establishes whether the method's velocity estimates are physically right, not just its integrated poses.
