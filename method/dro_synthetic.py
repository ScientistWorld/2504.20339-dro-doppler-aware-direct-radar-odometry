"""Compact DRO implementation for the synthetic benchmark.

This file implements the paper's computation at a smaller scale:
- split up/down chirps and GP-like infill for the Doppler image pair,
- maximize Doppler and direct intensity cross-correlation objectives,
- correct scans for continuous SE(2) motion and Doppler range distortion,
- update an image-like local map with a low-pass filter.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter1d, map_coordinates
from scipy.optimize import minimize


def rot2(theta: float) -> np.ndarray:
    c = np.cos(theta)
    s = np.sin(theta)
    return np.array([[c, -s], [s, c]], dtype=np.float64)


def integrate_body_velocity(v_body: np.ndarray, omega: float, dt: np.ndarray) -> np.ndarray:
    dt = np.asarray(dt, dtype=np.float64)
    if abs(omega) < 1e-9:
        return np.stack([v_body[0] * dt, v_body[1] * dt], axis=-1)
    s = np.sin(omega * dt)
    c = np.cos(omega * dt)
    return np.stack(
        [
            (s * v_body[0] - (1.0 - c) * v_body[1]) / omega,
            ((1.0 - c) * v_body[0] + s * v_body[1]) / omega,
        ],
        axis=-1,
    )


class LocalMap:
    def __init__(self, half_extent: float = 90.0, resolution: float = 0.35, alpha: float = 0.1):
        self.resolution = resolution
        self.alpha = alpha
        self.size = int(round(2 * half_extent / resolution)) + 1
        self.origin = np.array([-half_extent, -half_extent], dtype=np.float64)
        self.image = np.zeros((self.size, self.size), dtype=np.float32)
        self.initialized = False

    def xy_to_rc(self, xy: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        col = (xy[:, 0] - self.origin[0]) / self.resolution
        row = (xy[:, 1] - self.origin[1]) / self.resolution
        return row, col

    def query(self, xy: np.ndarray) -> np.ndarray:
        row, col = self.xy_to_rc(xy)
        return map_coordinates(self.image, [row, col], order=1, mode="constant", cval=0.0)

    def update_points(self, xy: np.ndarray, intensity: np.ndarray) -> None:
        row, col = self.xy_to_rc(xy)
        rr = np.rint(row).astype(np.int64)
        cc = np.rint(col).astype(np.int64)
        mask = (rr >= 0) & (rr < self.size) & (cc >= 0) & (cc < self.size) & (intensity > 0)
        new = np.zeros_like(self.image)
        np.maximum.at(new, (rr[mask], cc[mask]), intensity[mask])
        new = gaussian_filter1d(gaussian_filter1d(new, 1.0, axis=0), 1.0, axis=1)
        if self.initialized:
            self.image = (1.0 - self.alpha) * self.image + self.alpha * new
        else:
            self.image = new
            self.initialized = True


def preprocess(scan: np.ndarray) -> np.ndarray:
    x = scan.astype(np.float32).copy()
    std = np.std(x, axis=1, keepdims=True)
    x = np.maximum(0.0, x - 2.0 * std)
    mx = np.max(x, axis=1, keepdims=True)
    x = np.divide(x, np.maximum(mx, 1e-6), out=np.zeros_like(x), where=mx > 0)
    x = gaussian_filter1d(x, 1.5, axis=1)
    return x**3


def infill_up_down(scan: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Efficient local GP-style infill for alternating chirp rows.

    The released code precomputes squared-exponential GP convolution weights.
    Here the same local image-like infill role is implemented with a Gaussian
    row interpolation kernel to avoid full cubic GP inference.
    """
    smooth = preprocess(scan)
    up = np.zeros_like(smooth)
    down = np.zeros_like(smooth)
    up[0::2] = smooth[0::2]
    down[1::2] = smooth[1::2]
    for i in range(1, smooth.shape[0], 2):
        lo = max(0, i - 1)
        hi = min(smooth.shape[0] - 1, i + 1)
        up[i] = 0.5 * (up[lo] + up[hi])
    for i in range(0, smooth.shape[0], 2):
        lo = max(1, i - 1)
        hi = min(smooth.shape[0] - 2 if smooth.shape[0] % 2 else smooth.shape[0] - 1, i + 1)
        if lo <= hi:
            down[i] = 0.5 * (down[lo] + down[hi])
    return up, down


def corrected_points(
    scan: np.ndarray,
    azimuths: np.ndarray,
    ranges: np.ndarray,
    beam_times: np.ndarray,
    chirps: np.ndarray,
    start_pose: np.ndarray,
    v_body: np.ndarray,
    omega: float,
    beta: float,
    threshold: float = 0.08,
) -> tuple[np.ndarray, np.ndarray]:
    rows, cols = np.nonzero(scan > threshold)
    if len(rows) == 0:
        return np.zeros((0, 2)), np.zeros((0,), dtype=np.float32)
    al = azimuths[rows]
    dt = beam_times[rows]
    radial = np.cos(al) * v_body[0] + np.sin(al) * v_body[1]
    r = ranges[cols] + chirps[rows] * 0.5 * beta * radial
    local = np.stack([r * np.cos(al), r * np.sin(al)], axis=1)
    rel_pos = integrate_body_velocity(v_body, omega, dt)
    theta = start_pose[2] + omega * dt
    c = np.cos(theta)
    s = np.sin(theta)
    world = np.empty_like(local)
    world[:, 0] = start_pose[0] + c * local[:, 0] - s * local[:, 1] + np.cos(start_pose[2]) * rel_pos[:, 0] - np.sin(start_pose[2]) * rel_pos[:, 1]
    world[:, 1] = start_pose[1] + s * local[:, 0] + c * local[:, 1] + np.sin(start_pose[2]) * rel_pos[:, 0] + np.cos(start_pose[2]) * rel_pos[:, 1]
    return world, scan[rows, cols]


def doppler_score(v_body: np.ndarray, scan: np.ndarray, azimuths: np.ndarray, beta: float, range_res: float) -> float:
    up, down = infill_up_down(scan)
    radial = np.cos(azimuths) * v_body[0] + np.sin(azimuths) * v_body[1]
    # The synthetic generator writes up-chirp returns at true_range - d/2
    # and down-chirp returns at true_range + d/2. Querying the up-chirp image
    # at down_range - d therefore aligns both views of the same reflector.
    shift_bins = -beta * radial / range_res
    cols = np.arange(scan.shape[1], dtype=np.float64)[None, :] + shift_bins[:, None]
    rows = np.arange(scan.shape[0], dtype=np.float64)[:, None] * np.ones_like(cols)
    aligned = map_coordinates(up, [rows, cols], order=1, mode="constant", cval=0.0)
    return float(np.sum(down * aligned) / (np.sum(down > 0) + 1.0))


def direct_score(
    v_body: np.ndarray,
    scan: np.ndarray,
    lmap: LocalMap,
    azimuths: np.ndarray,
    ranges: np.ndarray,
    beam_times: np.ndarray,
    chirps: np.ndarray,
    start_pose: np.ndarray,
    omega: float,
    beta: float,
) -> float:
    xy, intensity = corrected_points(scan, azimuths, ranges, beam_times, chirps, start_pose, v_body, omega, beta)
    if len(intensity) == 0:
        return 0.0
    return float(np.sum(intensity * lmap.query(xy)) / (np.sum(intensity > 0) + 1.0))


def estimate_velocity(
    scan: np.ndarray,
    lmap: LocalMap,
    azimuths: np.ndarray,
    ranges: np.ndarray,
    beam_times: np.ndarray,
    chirps: np.ndarray,
    start_pose: np.ndarray,
    omega: float,
    beta: float,
    range_res: float,
    previous_v: np.ndarray,
    mode: str,
) -> np.ndarray:
    def objective(v: np.ndarray) -> float:
        v = np.asarray(v, dtype=np.float64)
        score = 0.0
        if mode in {"dro_g", "dro_gd"} and lmap.initialized:
            score += 1.0 * direct_score(v, scan, lmap, azimuths, ranges, beam_times, chirps, start_pose, omega, beta)
        if mode in {"dro_d", "dro_gd"}:
            score += 0.45 * doppler_score(v, scan, azimuths, beta, range_res)
        score -= 0.002 * float(np.sum((v - previous_v) ** 2))
        return -score

    best = previous_v
    best_value = objective(best)
    vx_grid = np.linspace(max(0.0, previous_v[0] - 2.5), previous_v[0] + 2.5, 17)
    vy_grid = np.linspace(previous_v[1] - 0.8, previous_v[1] + 0.8, 13)
    for vx in vx_grid:
        for vy in vy_grid:
            candidate = np.array([vx, vy], dtype=np.float64)
            value = objective(candidate)
            if value < best_value:
                best = candidate
                best_value = value

    result = minimize(
        objective,
        best,
        method="Nelder-Mead",
        options={
            "maxiter": 120,
            "xatol": 1e-3,
            "fatol": 1e-5,
            "initial_simplex": np.array([best, best + [0.25, 0.0], best + [0.0, 0.12]]),
        },
    )
    return np.asarray(result.x, dtype=np.float64)


def run_sequence(dataset: np.lib.npyio.NpzFile, scenario: str, mode: str) -> dict:
    meta = json.loads(str(dataset["manifest_json"].item()))[scenario]
    scans = dataset[f"{scenario}_scans"]
    azimuths = dataset[f"{scenario}_azimuths"]
    ranges = dataset[f"{scenario}_ranges"]
    beam_times = dataset[f"{scenario}_beam_times"]
    chirps = dataset[f"{scenario}_chirps"]
    gt = dataset[f"{scenario}_poses"]
    lmap = LocalMap()
    omega = float(meta["omega"])
    beta = float(meta["beta"])
    range_res = float(meta["range_res"])
    frame_period = float(meta["frame_period"])
    pose = np.array([gt[0, 1], gt[0, 2], gt[0, 3]], dtype=np.float64)
    v = np.array([4.5, 0.0], dtype=np.float64)
    trajectory = [[0.0, pose[0], pose[1], pose[2], v[0], v[1]]]
    scores = []
    for k, scan in enumerate(scans):
        if k > 0:
            v = estimate_velocity(scan, lmap, azimuths, ranges, beam_times, chirps, pose, omega, beta, range_res, v, mode)
            delta_local = integrate_body_velocity(v, omega, frame_period)
            pose[:2] += rot2(pose[2]) @ delta_local
            pose[2] += omega * frame_period
            trajectory.append([k * frame_period, pose[0], pose[1], pose[2], v[0], v[1]])
        xy, inten = corrected_points(scan, azimuths, ranges, beam_times, chirps, pose, v, omega, beta)
        lmap.update_points(xy, inten)
        scores.append({"frame": k, "vx": float(v[0]), "vy": float(v[1])})
    return {"trajectory": trajectory, "ground_truth": gt.tolist(), "frame_estimates": scores}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/synthetic_dro.npz")
    parser.add_argument("--output-dir", default="checkpoints/dro_synthetic")
    parser.add_argument("--mode", choices=["dro_g", "dro_d", "dro_gd"], default="dro_gd")
    args = parser.parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset = np.load(args.data, allow_pickle=False)
    results = {scenario: run_sequence(dataset, scenario, args.mode) for scenario in ["structured", "tunnel"]}
    with (out_dir / f"{args.mode}_predictions.json").open("w") as f:
        json.dump({"method": args.mode, "scenarios": results}, f, indent=2)
    print(out_dir / f"{args.mode}_predictions.json")


if __name__ == "__main__":
    main()
