"""Synthetic spinning FMCW radar sequences for the radar-odometry benchmark.

The real Doppler-enabled automotive dataset used in the paper is not fully
public. This generator keeps the sensing model of a spinning FMCW radar with a
triangular (alternating up/down chirp) modulation:

* the radar dish sweeps 360 degrees per scan; every azimuth beam is collected
  at its own timestamp while the vehicle keeps moving;
* each beam returns dense range intensities (a polar image row);
* the Doppler effect shifts every return along the beam by an amount
  proportional to the radial velocity, with opposite sign for up and down
  chirps;
* a yaw-rate gyroscope provides one bias-affected, noisy angular-rate sample
  per scan.

Vehicles follow smooth, time-varying speed and yaw-rate profiles that start
from rest. Scenes are either "structured" (buildings with gaps, poles,
clutter) or "tunnel" (two dense, featureless walls along the road).

Running this file writes the visible training split (inputs and labels).
Held-out sequences are produced elsewhere and only their inputs are public.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

FRAMES = 72
BEAMS = 180
BINS = 220
RANGE_RES = 0.35
FRAME_PERIOD = 0.25
BETA = 0.6
NOISE_STD = 0.015
GYRO_NOISE_STD = 0.001
RANGE_SIGMA_BINS = 1.15
BEAM_SIGMA = (2.0 * np.pi / BEAMS) * 0.42
RADAR_LEVER_ARM_M = 1.2
PATH_EXTENSION_M = 100.0

# Visible training split: (sequence name, scene type, seed).
TRAIN_SEQUENCES = (
    ("train_00", "structured", 101),
    ("train_01", "tunnel", 102),
    ("train_02", "structured", 103),
    ("train_03", "tunnel", 104),
)


def sensor_geometry() -> dict[str, np.ndarray]:
    return {
        "azimuths": np.linspace(-np.pi, np.pi, BEAMS, endpoint=False),
        "ranges": (np.arange(BINS, dtype=np.float64) + 0.5) * RANGE_RES,
        "beam_times": np.linspace(0.0, FRAME_PERIOD, BEAMS, endpoint=False),
        "chirps": np.where(np.arange(BEAMS) % 2 == 0, 1.0, -1.0),
    }


def sensor_manifest() -> dict:
    return {
        "beams": BEAMS,
        "bins": BINS,
        "range_res": RANGE_RES,
        "frame_period": FRAME_PERIOD,
        "beta": BETA,
    }


def smoothstep(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def sample_motion_profile(rng: np.random.Generator, scenario: str) -> dict:
    if scenario == "structured":
        v_cruise = rng.uniform(5.5, 8.0)
        kappa0 = rng.uniform(-0.012, 0.012)
        kappa1 = rng.uniform(0.006, 0.016)
    elif scenario == "tunnel":
        v_cruise = rng.uniform(6.5, 9.0)
        kappa0 = rng.uniform(-0.002, 0.002)
        kappa1 = rng.uniform(0.0, 0.0015)
    else:
        raise ValueError(f"unknown scenario: {scenario}")
    return {
        "scenario": scenario,
        "t_stop": rng.uniform(2.0, 2.75),
        "t_acc": rng.uniform(4.0, 6.0),
        "v_cruise": v_cruise,
        "speed_amp": rng.uniform(0.5, 1.3),
        "speed_period": rng.uniform(5.0, 9.0),
        "speed_phase": rng.uniform(0.0, 2.0 * np.pi),
        "kappa0": kappa0,
        "kappa1": kappa1,
        "kappa_period": rng.uniform(6.0, 12.0),
        "kappa_phase": rng.uniform(0.0, 2.0 * np.pi),
        "slip": rng.uniform(-0.04, 0.04),
        "gyro_bias": float(rng.choice([-1.0, 1.0]) * rng.uniform(0.001, 0.003)),
    }


def body_motion(profile: dict, t: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Body-frame forward/lateral velocity and yaw rate at times t."""
    ramp = smoothstep((t - profile["t_stop"]) / profile["t_acc"])
    oscillation = profile["speed_amp"] * np.sin(
        2.0 * np.pi * (t - profile["t_stop"]) / profile["speed_period"] + profile["speed_phase"]
    )
    speed = ramp * (profile["v_cruise"] + oscillation)
    kappa = profile["kappa0"] + profile["kappa1"] * np.sin(
        2.0 * np.pi * t / profile["kappa_period"] + profile["kappa_phase"]
    )
    omega = speed * kappa
    vx = speed
    vy = RADAR_LEVER_ARM_M * omega + profile["slip"] * ramp
    return vx, vy, omega


def _cumtrapz(values: np.ndarray, dt: float) -> np.ndarray:
    out = np.zeros_like(values)
    out[1:] = np.cumsum(0.5 * (values[1:] + values[:-1]) * dt)
    return out


def _spawn_rngs(seed: int) -> dict[str, np.random.Generator]:
    children = np.random.SeedSequence(int(seed)).spawn(4)
    return {
        name: np.random.default_rng(child)
        for name, child in zip(("profile", "scene", "noise", "gyro"), children)
    }


def simulate_motion(scenario: str, seed: int, frames: int = FRAMES) -> dict:
    """Continuous trajectory on a beam-rate grid, frame labels and gyro data."""
    rngs = _spawn_rngs(seed)
    profile = sample_motion_profile(rngs["profile"], scenario)
    dt = FRAME_PERIOD / BEAMS
    t = np.arange(frames * BEAMS + 1, dtype=np.float64) * dt
    vx, vy, omega = body_motion(profile, t)
    theta = _cumtrapz(omega, dt)
    c = np.cos(theta)
    s = np.sin(theta)
    x = _cumtrapz(c * vx - s * vy, dt)
    y = _cumtrapz(s * vx + c * vy, dt)

    frame_idx = np.arange(frames) * BEAMS
    window = frame_idx[:, None] + np.arange(BEAMS)[None, :]
    poses = np.column_stack([t[frame_idx], x[frame_idx], y[frame_idx], theta[frame_idx]])
    velocities = np.column_stack([vx[window].mean(axis=1), vy[window].mean(axis=1)])
    omega_frame = omega[window].mean(axis=1)
    gyro = omega_frame + profile["gyro_bias"] + rngs["gyro"].normal(0.0, GYRO_NOISE_STD, size=frames)
    return {
        "profile": profile,
        "rngs": rngs,
        "t": t,
        "x": x,
        "y": y,
        "theta": theta,
        "vx": vx,
        "vy": vy,
        "poses": poses,
        "velocities": velocities,
        "gyro_yaw": gyro,
    }


def _path_polyline(x: np.ndarray, y: np.ndarray, theta: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    pts = np.column_stack([x, y])
    keep = [0]
    for i in range(1, len(pts)):
        if np.hypot(*(pts[i] - pts[keep[-1]])) >= 0.25:
            keep.append(i)
    core = pts[keep]
    d0 = np.array([np.cos(theta[0]), np.sin(theta[0])])
    d1 = np.array([np.cos(theta[-1]), np.sin(theta[-1])])
    # Scene extends beyond radar range at both ends: no visible wall ends.
    back = core[0] - np.outer(np.arange(PATH_EXTENSION_M, 0.0, -0.5), d0)
    fwd = core[-1] + np.outer(np.arange(0.5, PATH_EXTENSION_M, 0.5), d1)
    poly = np.vstack([back, core, fwd])
    s = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(poly, axis=0).T))])
    return poly, s


def _along_path(poly: np.ndarray, s: np.ndarray, query: np.ndarray, lateral: np.ndarray) -> np.ndarray:
    px = np.interp(query, s, poly[:, 0])
    py = np.interp(query, s, poly[:, 1])
    tx = np.interp(query + 0.5, s, poly[:, 0]) - np.interp(query - 0.5, s, poly[:, 0])
    ty = np.interp(query + 0.5, s, poly[:, 1]) - np.interp(query - 0.5, s, poly[:, 1])
    norm = np.maximum(np.hypot(tx, ty), 1e-9)
    nx = -ty / norm
    ny = tx / norm
    return np.column_stack([px + lateral * nx, py + lateral * ny])


def make_landmarks(motion: dict, scenario: str) -> tuple[np.ndarray, np.ndarray]:
    rng = motion["rngs"]["scene"]
    poly, s = _path_polyline(motion["x"], motion["y"], motion["theta"])
    s_max = float(s[-1])
    points = []
    amps = []
    if scenario == "structured":
        for side in (-1.0, 1.0):
            offset = rng.uniform(7.0, 9.5)
            q = np.arange(rng.uniform(0.0, 2.0), s_max, 2.0)
            q = q + rng.normal(0.0, 0.15, size=q.shape)
            q = q[rng.random(q.shape) > 0.15]
            lateral = side * (offset + rng.normal(0.0, 0.18, size=q.shape))
            points.append(_along_path(poly, s, q, lateral))
            amps.append(np.ones(q.shape))
        n_clutter = int(s_max / 1.6)
        q = rng.uniform(0.0, s_max, size=n_clutter)
        lateral = rng.choice([-1.0, 1.0], size=n_clutter) * rng.uniform(10.0, 20.0, size=n_clutter)
        points.append(_along_path(poly, s, q, lateral))
        amps.append(rng.uniform(0.4, 1.0, size=n_clutter))
        q = np.cumsum(rng.uniform(12.0, 20.0, size=int(s_max / 12.0) + 1))
        q = q[q < s_max]
        sides = np.where(np.arange(len(q)) % 2 == 0, 1.0, -1.0)
        lateral = sides * rng.uniform(3.5, 5.0, size=q.shape)
        points.append(_along_path(poly, s, q, lateral))
        amps.append(np.full(q.shape, 0.8))
    elif scenario == "tunnel":
        for side in (-1.0, 1.0):
            # Dense, smooth walls (spacing below the range/azimuth
            # resolution) carry no along-track structure.
            offset = rng.uniform(4.6, 5.6)
            q = np.arange(0.0, s_max, 0.2)
            lateral = side * (offset + rng.normal(0.0, 0.02, size=q.shape))
            points.append(_along_path(poly, s, q, lateral))
            amps.append(np.full(q.shape, 0.25))
    else:
        raise ValueError(f"unknown scenario: {scenario}")
    return np.vstack(points), np.concatenate(amps)


def render_scans(motion: dict, landmarks: np.ndarray, amps: np.ndarray, frames: int) -> np.ndarray:
    geo = sensor_geometry()
    azimuths = geo["azimuths"]
    chirps = geo["chirps"]
    max_range = geo["ranges"][-1] - 1.0
    rng = motion["rngs"]["noise"]
    offsets = np.arange(-4, 5)
    scans = np.zeros((frames, BEAMS, BINS), dtype=np.uint8)
    for k in range(frames):
        scan = np.zeros((BEAMS, BINS), dtype=np.float64)
        for i in range(BEAMS):
            f = k * BEAMS + i
            c = np.cos(motion["theta"][f])
            s = np.sin(motion["theta"][f])
            dx = landmarks[:, 0] - motion["x"][f]
            dy = landmarks[:, 1] - motion["y"][f]
            rel_x = c * dx + s * dy
            rel_y = -s * dx + c * dy
            r = np.hypot(rel_x, rel_y)
            bearing_err = np.arctan2(rel_y, rel_x) - azimuths[i]
            bearing_err = np.arctan2(np.sin(bearing_err), np.cos(bearing_err))
            mask = (r > 1.0) & (r < max_range) & (np.abs(bearing_err) < 3.0 * BEAM_SIGMA)
            if not np.any(mask):
                continue
            radial = np.cos(azimuths[i]) * motion["vx"][f] + np.sin(azimuths[i]) * motion["vy"][f]
            measured_r = r[mask] - chirps[i] * 0.5 * BETA * radial
            bins_float = measured_r / RANGE_RES - 0.5
            weights = amps[mask] * np.exp(-0.5 * (bearing_err[mask] / BEAM_SIGMA) ** 2)
            idx = np.rint(bins_float).astype(np.int64)[:, None] + offsets[None, :]
            vals = weights[:, None] * np.exp(-0.5 * ((idx - bins_float[:, None]) / RANGE_SIGMA_BINS) ** 2)
            valid = (idx >= 0) & (idx < BINS)
            np.add.at(scan[i], idx[valid], vals[valid])
        scan += rng.normal(0.0, NOISE_STD, size=scan.shape)
        scan[scan < 0] = 0.0
        row_max = scan.max(axis=1, keepdims=True)
        scan = np.divide(scan, np.maximum(row_max, 1e-6), out=np.zeros_like(scan), where=row_max > 0)
        scans[k] = np.rint(np.clip(scan, 0.0, 1.0) * 255.0).astype(np.uint8)
    return scans


def render_sequence(scenario: str, seed: int, frames: int = FRAMES) -> dict:
    motion = simulate_motion(scenario, seed, frames)
    landmarks, amps = make_landmarks(motion, scenario)
    scans = render_scans(motion, landmarks, amps, frames)
    return {
        "scenario": scenario,
        "scans": scans,
        "gyro_yaw": motion["gyro_yaw"].astype(np.float32),
        "frame_times": motion["poses"][:, 0].astype(np.float64),
        "poses": motion["poses"].astype(np.float64),
        "velocities": motion["velocities"].astype(np.float64),
    }


def write_dataset(path: Path, sequences: dict[str, dict], include_labels: bool) -> None:
    geo = sensor_geometry()
    arrays: dict[str, np.ndarray] = {key: value.astype(np.float32) for key, value in geo.items()}
    manifest: dict = {"sensor": sensor_manifest(), "sequences": {}}
    for name, seq in sequences.items():
        arrays[f"{name}_scans"] = seq["scans"]
        arrays[f"{name}_gyro_yaw"] = seq["gyro_yaw"]
        arrays[f"{name}_frame_times"] = seq["frame_times"]
        entry = {"frames": int(seq["scans"].shape[0])}
        if include_labels:
            entry["scenario"] = seq["scenario"]
            arrays[f"{name}_poses"] = seq["poses"]
            arrays[f"{name}_velocities"] = seq["velocities"]
        manifest["sequences"][name] = entry
    arrays["manifest_json"] = np.array(json.dumps(manifest, indent=2, sort_keys=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **arrays)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", default="data/train.npz")
    args = parser.parse_args()
    sequences = {name: render_sequence(scenario, seed) for name, scenario, seed in TRAIN_SEQUENCES}
    write_dataset(Path(args.output), sequences, include_labels=True)
    print(f"wrote {args.output} ({len(sequences)} labelled sequences)")


if __name__ == "__main__":
    main()
