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
from scipy.ndimage import convolve, gaussian_filter1d, map_coordinates


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


def squared_exponential_kernel(x1: np.ndarray, x2: np.ndarray, lengthscale_az: float, lengthscale_range: float) -> np.ndarray:
    a = x1.astype(np.float64).copy()
    b = x2.astype(np.float64).copy()
    a[:, 0] /= lengthscale_az
    b[:, 0] /= lengthscale_az
    a[:, 1] /= lengthscale_range
    b[:, 1] /= lengthscale_range
    sqdist = np.sum((a[:, None, :] - b[None, :, :]) ** 2, axis=2)
    return np.exp(-0.5 * sqdist)


def gp_convolution_weights(
    size_az: int = 4,
    size_range: int = 4,
    lengthscale_az: float = 3.0,
    lengthscale_range: float = 3.0,
    noise: float = 0.08,
) -> tuple[np.ndarray, np.ndarray]:
    """Precompute the local GP weights used to infill alternating chirp rows."""
    x = np.arange(-size_az, size_az + 1)
    y = np.arange(-size_range, size_range + 1)
    smooth_x = x[x % 2 == 0].astype(np.float64)
    interp_x = x[x % 2 != 0].astype(np.float64)

    def weights(xs: np.ndarray) -> np.ndarray:
        xx, yy = np.meshgrid(xs, y, indexing="ij")
        support = np.stack([xx.ravel(), yy.ravel()], axis=1)
        k_xx = squared_exponential_kernel(support, support, lengthscale_az, lengthscale_range)
        k_xx += noise**2 * np.eye(len(support))
        k_star = squared_exponential_kernel(np.array([[0.0, 0.0]]), support, lengthscale_az, lengthscale_range)
        return (k_star @ np.linalg.inv(k_xx)).reshape(len(xs), len(y)).astype(np.float32)

    return weights(smooth_x), weights(interp_x)


GP_SMOOTH_WEIGHTS, GP_INTERP_WEIGHTS = gp_convolution_weights()


def postprocess_gp_image(image: np.ndarray) -> np.ndarray:
    x = image.astype(np.float32).copy()
    std = np.std(x, axis=1, keepdims=True)
    x = np.maximum(0.0, x - 2.0 * std)
    x = gaussian_filter1d(x, 3.0, axis=0)
    mx = np.max(x, axis=1, keepdims=True)
    x = np.divide(x, np.maximum(mx, 1e-6), out=np.zeros_like(x), where=mx > 0)
    return x**3


def infill_up_down(scan: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Split alternating chirps and infill missing rows with local GP regression."""
    raw = scan.astype(np.float32)
    even = raw[0::2] - float(np.mean(raw[0::2]))
    odd = raw[1::2] - float(np.mean(raw[1::2]))

    even_smooth = convolve(even, GP_SMOOTH_WEIGHTS, mode="constant", cval=0.0)
    even_interp = convolve(even, GP_INTERP_WEIGHTS, mode="constant", cval=0.0)
    odd_smooth = convolve(odd, GP_SMOOTH_WEIGHTS, mode="constant", cval=0.0)
    odd_interp = convolve(odd, GP_INTERP_WEIGHTS, mode="constant", cval=0.0)

    up = np.zeros_like(raw)
    down = np.zeros_like(raw)
    up[0::2] = even_smooth[: up[0::2].shape[0]]
    if up[1::2].shape[0] > 0:
        up[1::2] = even_interp[: up[1::2].shape[0]]
    down[1::2] = odd_smooth[: down[1::2].shape[0]]
    if down[0::2].shape[0] > 0:
        down[0::2] = odd_interp[: down[0::2].shape[0]]

    up = postprocess_gp_image(up)
    down = postprocess_gp_image(down)
    up[:4] = 0
    up[-4:] = 0
    down[:4] = 0
    down[-4:] = 0
    up[:, :4] = 0
    up[:, -4:] = 0
    down[:, :4] = 0
    down[:, -4:] = 0
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


def _shift_row(row: np.ndarray, shift: int) -> np.ndarray:
    out = np.zeros_like(row)
    if shift > 0:
        out[shift:] = row[:-shift]
    elif shift < 0:
        out[:shift] = row[-shift:]
    else:
        out[:] = row
    return out


def doppler_velocity_initializer(scan: np.ndarray, azimuths: np.ndarray, beta: float, range_res: float) -> np.ndarray | None:
    """Estimate body velocity from per-row Doppler cross-correlation shifts.

    This is an explicit small-scale equivalent of maximizing the paper's
    Doppler objective: find the range shift that best aligns up/down chirp
    intensity images, then solve the radial-velocity relation
    shift_bins = beta / range_res * [cos(a), sin(a)] v_body for the
    integer row-moving convention used by _shift_row().
    """
    up, down = infill_up_down(scan)
    max_shift = max(3, int(round(10.0 * beta / range_res)))
    shifts = []
    rows = []
    weights = []
    for i, alpha in enumerate(azimuths):
        if np.max(up[i]) <= 0 or np.max(down[i]) <= 0:
            continue
        best_shift = 0
        best_score = -np.inf
        for shift in range(-max_shift, max_shift + 1):
            score = float(np.dot(down[i], _shift_row(up[i], shift)))
            if score > best_score:
                best_score = score
                best_shift = shift
        if best_score <= 0:
            continue
        shifts.append(best_shift)
        rows.append([np.cos(alpha), np.sin(alpha)])
        weights.append(best_score)
    if len(shifts) < 8:
        return None
    a = np.asarray(rows, dtype=np.float64)
    b = np.asarray(shifts, dtype=np.float64) * range_res / beta
    w = np.sqrt(np.asarray(weights, dtype=np.float64) / (np.max(weights) + 1e-9))
    aw = a * w[:, None]
    bw = b * w
    v, *_ = np.linalg.lstsq(aw, bw, rcond=None)
    if not np.all(np.isfinite(v)):
        return None
    return np.clip(v, [-2.0, -3.0], [12.0, 3.0])


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
    doppler_init = None
    if mode in {"dro_d", "dro_gd"}:
        doppler_init = doppler_velocity_initializer(scan, azimuths, beta, range_res)
    doppler_anchor = None
    if mode == "dro_gd":
        doppler_anchor = estimate_velocity(
            scan,
            lmap,
            azimuths,
            ranges,
            beam_times,
            chirps,
            start_pose,
            omega,
            beta,
            range_res,
            previous_v,
            "dro_d",
        )

    def score_fn(v: np.ndarray) -> float:
        v = np.asarray(v, dtype=np.float64)
        score = 0.0
        if mode in {"dro_g", "dro_gd"} and lmap.initialized:
            direct_weight = 0.12 if mode == "dro_gd" and doppler_init is not None else 1.0
            score += direct_weight * direct_score(v, scan, lmap, azimuths, ranges, beam_times, chirps, start_pose, omega, beta)
        if mode in {"dro_d", "dro_gd"}:
            doppler_weight = 2.0 if mode == "dro_gd" else 0.9
            score += doppler_weight * doppler_score(v, scan, azimuths, beta, range_res)
        score -= 0.0002 * float(np.sum((v - previous_v) ** 2))
        if mode == "dro_gd" and doppler_anchor is not None:
            score -= 0.04 * float(np.sum((v - doppler_anchor) ** 2))
        return score

    if mode == "dro_gd" and doppler_anchor is not None:
        best = doppler_anchor
    else:
        best = doppler_init if doppler_init is not None else previous_v
    best_value = -score_fn(best)
    vx_center = best[0]
    vy_center = best[1]
    vx_grid = np.linspace(max(0.0, vx_center - 2.5), vx_center + 2.5, 21)
    vy_grid = np.linspace(vy_center - 1.0, vy_center + 1.0, 17)
    for vx in vx_grid:
        for vy in vy_grid:
            candidate = np.array([vx, vy], dtype=np.float64)
            value = -score_fn(candidate)
            if value < best_value:
                best = candidate
                best_value = value

    state = best.astype(np.float64)
    step = 0.2
    eps = np.array([0.03, 0.03], dtype=np.float64)
    current = score_fn(state)
    for _ in range(80):
        grad = np.array(
            [
                (score_fn(state + [eps[0], 0.0]) - score_fn(state - [eps[0], 0.0])) / (2.0 * eps[0]),
                (score_fn(state + [0.0, eps[1]]) - score_fn(state - [0.0, eps[1]])) / (2.0 * eps[1]),
            ],
            dtype=np.float64,
        )
        norm = np.linalg.norm(grad)
        if norm < 1e-9:
            break
        candidate = state + step * grad / norm
        candidate = np.clip(candidate, [0.0, -3.0], [12.0, 3.0])
        value = score_fn(candidate)
        if value >= current:
            state = candidate
            current = value
        else:
            step *= 0.5
            if step < 1e-3:
                break
    return state


def run_sequence(dataset: np.lib.npyio.NpzFile, scenario: str, mode: str) -> dict:
    meta = json.loads(str(dataset["manifest_json"].item()))[scenario]
    scans = dataset[f"{scenario}_scans"]
    azimuths = dataset[f"{scenario}_azimuths"]
    ranges = dataset[f"{scenario}_ranges"]
    beam_times = dataset[f"{scenario}_beam_times"]
    chirps = dataset[f"{scenario}_chirps"]
    gyro_yaw = dataset[f"{scenario}_gyro_yaw"]
    gt = dataset[f"{scenario}_poses"]
    lmap = LocalMap()
    beta = float(meta["beta"])
    range_res = float(meta["range_res"])
    frame_period = float(meta["frame_period"])
    pose = np.array([gt[0, 1], gt[0, 2], gt[0, 3]], dtype=np.float64)
    v = np.array([4.5, 0.0], dtype=np.float64)
    trajectory = [[0.0, pose[0], pose[1], pose[2], v[0], v[1]]]
    scores = []
    for k, scan in enumerate(scans):
        omega = float(gyro_yaw[k])
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
