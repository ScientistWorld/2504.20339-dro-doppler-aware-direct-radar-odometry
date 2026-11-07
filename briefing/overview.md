# Overview

The paper introduces DRO, a Doppler-aware direct radar odometry method for spinning FMCW radars. It aligns dense radar intensity scans to an online local map, compensating for continuous scan motion and Doppler range distortion. With triangular chirps, it also estimates velocity from the Doppler shift between up- and down-chirp radar images.

This workspace packages a compact reproduction on a procedurally rendered spinning-radar benchmark. The original datasets are either very large public robotics datasets or, for the central Doppler-enabled claim, not public. The benchmark keeps the sensing model and the paper's estimation procedure at smaller scale:

- vehicles start at rest, then drive with time-varying speed and yaw rate;
- a biased, noisy gyroscope;
- landmark-rich streets and featureless tunnels.

Four labelled training sequences are visible. Six held-out sequences are scored by a hidden evaluator, whose labels and comparator rows live only in `eval/test/`.
