"""Compact DRO implementation for the synthetic benchmark.

This file implements the paper's computation at a smaller scale:
- split up/down chirps and GP infill for the Doppler image pair,
- maximize Doppler and direct intensity cross-correlation objectives,
- correct scans for continuous SE(2) motion and Doppler range distortion,
- update an image-like local map with a low-pass filter,
- integrate the gyroscope for orientation, with the paper's stationary-
  vehicle gyro-bias heuristic (Sec. IV-D2).

Each scan k is registered with the trajectory starting at the pose estimated
for the end of scan k-1 (= start of scan k); the estimated constant
body-frame velocity of scan k then propagates the pose to the next scan.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import correlate, gaussian_filter1d, map_coordinates

DEFAULT_CONFIG = {
    "gd_direct_weight": 0.12,
    "gd_doppler_weight": 2.0,
    "gd_anchor_weight": 0.04,
    "d_doppler_weight": 0.9,
    "velocity_prior_weight": 0.0002,
    "gyro_bias_estimation": True,
    "stationary_speed_mps": 0.05,
    "gyro_bias_init_samples": 5,
    "gyro_bias_lowpass": 0.1,
    "map_update_gamma": 0.1,
}
CONFIG_PATH = Path(__file__).resolve().parent / "dro_config.json"


def load_config(path: Path | None = CONFIG_PATH) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if path is not None and Path(path).is_file():
        stored = json.loads(Path(path).read_text())
        cfg.update({k: stored[k] for k in DEFAULT_CONFIG if k in stored})
    return cfg


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
    def __init__(self, half_extent: float = 200.0, resolution: float = 0.35, alpha: float = 0.1):
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

    even_smooth = correlate(even, GP_SMOOTH_WEIGHTS, mode="constant", cval=0.0)
    even_interp = correlate(even, GP_INTERP_WEIGHTS, mode="constant", cval=0.0)
    odd_smooth = correlate(odd, GP_SMOOTH_WEIGHTS, mode="constant", cval=0.0)
    odd_interp = correlate(odd, GP_INTERP_WEIGHTS, mode="constant", cval=0.0)

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


def doppler_score(v_body: np.ndarray, infill: tuple[np.ndarray, np.ndarray], azimuths: np.ndarray, beta: float, range_res: float) -> float:
    up, down = infill
    radial = np.cos(azimuths) * v_body[0] + np.sin(azimuths) * v_body[1]
    # Up-chirp returns sit at true_range - d/2 and down-chirp returns at
    # true_range + d/2. Querying the up-chirp image at down_range - d
    # therefore aligns both views of the same reflector.
    shift_bins = -beta * radial / range_res
    cols = np.arange(down.shape[1], dtype=np.float64)[None, :] + shift_bins[:, None]
    rows = np.arange(down.shape[0], dtype=np.float64)[:, None] * np.ones_like(cols)
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


def doppler_velocity_initializer(infill: tuple[np.ndarray, np.ndarray], azimuths: np.ndarray, beta: float, range_res: float) -> np.ndarray | None:
    """Estimate body velocity from per-row Doppler cross-correlation shifts.

    Find the integer range shift that best aligns up/down chirp intensity rows,
    then solve shift_bins = beta / range_res * [cos(a), sin(a)] v_body.
    """
    up, down = infill
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
    v, *_ = np.linalg.lstsq(a * w[:, None], b * w, rcond=None)
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
    infill: tuple[np.ndarray, np.ndarray] | None,
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
    cfg: dict,
) -> np.ndarray:
    uses_doppler = mode in {"dro_d", "dro_gd"}
    uses_direct = mode in {"dro_g", "dro_gd"} and lmap.initialized
    if not uses_doppler and not uses_direct:
        return np.asarray(previous_v, dtype=np.float64).copy()
    if uses_doppler and infill is None:
        infill = infill_up_down(scan)

    doppler_init = doppler_velocity_initializer(infill, azimuths, beta, range_res) if uses_doppler else None
    doppler_anchor = None
    if mode == "dro_gd":
        doppler_anchor = estimate_velocity(
            scan, infill, lmap, azimuths, ranges, beam_times, chirps, start_pose,
            omega, beta, range_res, previous_v, "dro_d", cfg,
        )

    def score_fn(v: np.ndarray) -> float:
        v = np.asarray(v, dtype=np.float64)
        score = 0.0
        if uses_direct:
            direct_weight = cfg["gd_direct_weight"] if mode == "dro_gd" and doppler_init is not None else 1.0
            score += direct_weight * direct_score(v, scan, lmap, azimuths, ranges, beam_times, chirps, start_pose, omega, beta)
        if uses_doppler:
            doppler_weight = cfg["gd_doppler_weight"] if mode == "dro_gd" else cfg["d_doppler_weight"]
            score += doppler_weight * doppler_score(v, infill, azimuths, beta, range_res)
        score -= cfg["velocity_prior_weight"] * float(np.sum((v - previous_v) ** 2))
        if mode == "dro_gd" and doppler_anchor is not None:
            score -= cfg["gd_anchor_weight"] * float(np.sum((v - doppler_anchor) ** 2))
        return score

    if mode == "dro_gd" and doppler_anchor is not None:
        best = doppler_anchor
    else:
        best = doppler_init if doppler_init is not None else np.asarray(previous_v, dtype=np.float64)
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

    # Normalized gradient ascent, step halved on every non-ascending step.
    state = np.asarray(best, dtype=np.float64)
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


class GyroBias:
    """Stationary-vehicle gyro bias heuristic (paper Sec. IV-D2).

    The bias is initialized by averaging the first Q raw gyro samples taken
    while the velocity estimate is below a threshold, then low-pass updated
    whenever the vehicle is again estimated to be stationary. While fewer than
    Q samples exist, their running mean is applied provisionally so the
    uncorrected bias does not rotate the map during the initial stop.
    """

    def __init__(self, enabled: bool, threshold: float, init_samples: int, lowpass: float):
        self.enabled = enabled
        self.threshold = threshold
        self.init_samples = init_samples
        self.lowpass = lowpass
        self.value = 0.0
        self.samples: list[float] = []
        self.initialized = False
        self.stationary_frames = 0

    def update(self, v: np.ndarray, raw_rate: float) -> bool:
        if not self.enabled or float(np.linalg.norm(v)) >= self.threshold:
            return False
        self.stationary_frames += 1
        if not self.initialized:
            self.samples.append(raw_rate)
            self.value = float(np.mean(self.samples))
            self.initialized = len(self.samples) >= self.init_samples
            return True
        self.value = (1.0 - self.lowpass) * self.value + self.lowpass * raw_rate
        return True


def load_sequences(paths: list[str]) -> list[tuple[str, dict, dict]]:
    sequences = []
    for path in paths:
        with np.load(path, allow_pickle=False) as data:
            manifest = json.loads(str(data["manifest_json"].item()))
            shared = {key: np.asarray(data[key], dtype=np.float64) for key in ("azimuths", "ranges", "beam_times", "chirps")}
            for name in sorted(manifest["sequences"]):
                seq = dict(shared)
                seq["scans"] = np.asarray(data[f"{name}_scans"])
                seq["gyro_yaw"] = np.asarray(data[f"{name}_gyro_yaw"], dtype=np.float64)
                seq["frame_times"] = np.asarray(data[f"{name}_frame_times"], dtype=np.float64)
                sequences.append((name, seq, manifest["sensor"]))
    return sequences


def run_sequence(seq: dict, sensor: dict, mode: str, cfg: dict) -> dict:
    azimuths = seq["azimuths"]
    ranges = seq["ranges"]
    beam_times = seq["beam_times"]
    chirps = seq["chirps"]
    gyro = seq["gyro_yaw"]
    beta = float(sensor["beta"])
    range_res = float(sensor["range_res"])
    frame_period = float(sensor["frame_period"])

    lmap = LocalMap(alpha=cfg["map_update_gamma"])
    bias = GyroBias(cfg["gyro_bias_estimation"], cfg["stationary_speed_mps"], int(cfg["gyro_bias_init_samples"]), cfg["gyro_bias_lowpass"])
    pose = np.zeros(3, dtype=np.float64)
    v = np.zeros(2, dtype=np.float64)
    trajectory = []
    for k in range(len(seq["scans"])):
        scan = seq["scans"][k].astype(np.float32) / 255.0
        infill = infill_up_down(scan) if mode in {"dro_d", "dro_gd"} else None
        omega = float(gyro[k]) - bias.value
        v = estimate_velocity(scan, infill, lmap, azimuths, ranges, beam_times, chirps, pose, omega, beta, range_res, v, mode, cfg)
        if bias.update(v, float(gyro[k])):
            omega = float(gyro[k]) - bias.value
        trajectory.append([float(seq["frame_times"][k]), float(pose[0]), float(pose[1]), float(pose[2]), float(v[0]), float(v[1])])
        xy, inten = corrected_points(scan, azimuths, ranges, beam_times, chirps, pose, v, omega, beta)
        lmap.update_points(xy, inten)
        pose[:2] += rot2(pose[2]) @ integrate_body_velocity(v, omega, frame_period)
        pose[2] += omega * frame_period
    return {
        "trajectory": trajectory,
        "gyro_bias_estimate": float(bias.value),
        "stationary_frames": int(bias.stationary_frames),
    }


def cache_key(name: str, seq: dict, mode: str, cfg: dict) -> str:
    h = hashlib.sha1()
    h.update(Path(__file__).read_bytes())
    h.update(json.dumps({"mode": mode, "cfg": cfg}, sort_keys=True).encode())
    for key in ("scans", "gyro_yaw", "frame_times"):
        h.update(np.ascontiguousarray(seq[key]).tobytes())
    return f"{name}__{mode}__{h.hexdigest()[:16]}.json"


def run_all(inputs: list[str], mode: str, cfg: dict, cache_dir: Path | None, only: set[str] | None = None) -> dict:
    results = {}
    for name, seq, sensor in load_sequences(inputs):
        if only is not None and name not in only:
            continue
        cached = cache_dir / cache_key(name, seq, mode, cfg) if cache_dir is not None else None
        if cached is not None and cached.is_file():
            results[name] = json.loads(cached.read_text())
            continue
        results[name] = run_sequence(seq, sensor, mode, cfg)
        if cached is not None:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_text(json.dumps(results[name]))
        print(f"{mode} {name}: done", flush=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["dro_g", "dro_d", "dro_gd"], default="dro_gd")
    parser.add_argument("--inputs", nargs="+", default=["data/train.npz", "data/test_inputs.npz"])
    parser.add_argument("--output", default=None)
    parser.add_argument("--name", default=None, help="method name written into the artifact (default: mode)")
    parser.add_argument("--config", default=str(CONFIG_PATH))
    parser.add_argument("--no-gyro-bias", action="store_true", help="ablation: integrate raw gyro rates")
    parser.add_argument("--cache-dir", default="checkpoints/cache")
    args = parser.parse_args()

    cfg = load_config(Path(args.config))
    if args.no_gyro_bias:
        cfg["gyro_bias_estimation"] = False
    name = args.name or args.mode
    output = Path(args.output or f"checkpoints/dro_synthetic/{name}_predictions.json")
    results = run_all(args.inputs, args.mode, cfg, Path(args.cache_dir) if args.cache_dir else None)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"method": name, "mode": args.mode, "config": cfg, "sequences": results}, indent=1))
    print(output)


if __name__ == "__main__":
    main()
