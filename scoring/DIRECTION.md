# Research Direction

Work within Doppler-aware direct radar odometry for spinning FMCW radar. The intended improvement space is better use of dense radar intensity, Doppler shift constraints, continuous-time scan correction, gyro-aided motion modeling, and local-map registration.

Acceptable research directions include changing how up/down chirp evidence is infilled, how the direct and Doppler objectives are weighted or optimized, how scans are corrected for range distortion and motion distortion, and how the local radar map is maintained.

Do not switch to unrelated localization paradigms that bypass the paper's claim, such as training a generic regressor from scans to poses, fitting a trajectory smoother to the ground truth, replacing radar odometry with an external SLAM system, or using privileged ground-truth trajectory information at inference time.
