# Problem Definition

Estimate the planar (SE(2)) trajectory of a vehicle carrying a 360-degree spinning FMCW radar and a yaw-axis gyroscope.

Each radar scan is a polar intensity image (`uint8`, 180 azimuth rows x 220 range bins, 0.35 m per bin, about 77 m maximum range). The dish sweeps one revolution per scan (0.25 s), so every row is collected at its own timestamp while the vehicle keeps moving. Consecutive rows alternate between up-chirp and down-chirp frequency modulation (`chirps` = +1 / -1). The returned range of a reflector is shifted along the beam by an amount proportional to its radial velocity: by `-beta * u / 2` on up-chirp rows and `+beta * u / 2` on down-chirp rows, where `u` is the body-frame velocity projected on the beam direction and `beta` is given in the sensor metadata. The gyroscope provides one yaw-rate sample per scan: the mean rate over that scan plus an unknown constant bias and white noise.

Every sequence starts with the vehicle at rest at the origin, heading 0. It then drives with speed, path curvature and side slip that vary smoothly and randomly over time. The radar is mounted on the vehicle's longitudinal axis, `radar_ahead_of_rear_axle_m` (sensor metadata) ahead of the rear axle. Scenes are either landmark-rich streets or long featureless tunnels.

## Inputs

- `data/train.npz`: labelled training sequences. Per sequence `<name>_scans`, `<name>_gyro_yaw`, `<name>_frame_times`, plus labels `<name>_poses` (`[t, x, y, heading]` at each scan start) and `<name>_velocities` (body-frame velocity averaged over each scan). Shared sensor arrays: `azimuths`, `ranges`, `beam_times` (row time offset within a scan), `chirps`. `manifest_json` holds the sensor constants and the list of sequences, including each training sequence's scene type.
- `data/test_inputs.npz`: held-out sequences in the same format, without labels or scene types.

## Output

One JSON artifact per method, named `*_predictions.json`, stored under `checkpoints/`, `method/` or `baseline/`:

```json
{"method": "my_method",
 "sequences": {"train_00": {"trajectory": [[t, x, y, heading, vx_body, vy_body], ...]},
               "test_00":  {"trajectory": [...]}}}
```

The artifact needs one row per scan for every sequence of a split, in the same coordinate convention as the labels: the first pose is the origin with heading 0. `t` is the scan start time from `<name>_frame_times`. `x, y, heading` is the pose at that time. `vx_body, vy_body` is the estimated body-frame velocity during that scan; it must describe the motion from this row's pose to the next row's pose (see `briefing/evaluation.md`). Extra fields are ignored.

The evaluators reserve the names `fixed_velocity_gyro`, `dead_reckoning`, `dro_d` and `dro_g` for their fixed comparator rows. Artifacts that use these names are ignored.
