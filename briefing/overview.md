# Overview

The paper introduces DRO, a Doppler-aware direct radar odometry method for spinning FMCW radars. It aligns dense radar intensity scans to an online local map while compensating for continuous scan motion and Doppler range distortion. With triangular chirps, it also estimates velocity from the Doppler shift between up- and down-chirp radar images.

This workspace packages a compact reproduction on a controlled synthetic spinning-radar benchmark. The original full-scale datasets are either very large public robotics datasets or, for the central Doppler-enabled claim, not fully public, so the benchmark preserves the sensing and optimization procedure at smaller scale.
