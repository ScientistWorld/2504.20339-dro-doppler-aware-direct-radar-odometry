"""Synthetic spinning FMCW radar data for the DRO reproduction.

The real Doppler-enabled automotive dataset used in the paper is not fully
public. This generator keeps the paper's sensing model: a scanning radar emits
azimuth beams over time, observes dense range intensity, and Doppler shifts
alternate up/down chirps by an amount proportional to radial velocity.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def rot2(theta: float) -> np.ndarray:
    c = np.cos(theta)
    s = np.sin(theta)
    return np.array([[c, -s], [s, c]], dtype=np.float64)


def integrate_body_velocity(v_body: np.ndarray, omega: float, dt: float) -> np.ndarray:
    if abs(omega) < 1e-9:
        return v_body * dt
    s = np.sin(omega * dt)
    c = np.cos(omega * dt)
    return np.array(
        [
            (s * v_body[0] - (1.0 - c) * v_body[1]) / omega,
            ((1.0 - c) * v_body[0] + s * v_body[1]) / omega,
        ],
        dtype=np.float64,
    )


def make_landmarks(scenario: str, rng: np.random.Generator) -> np.ndarray:
    if scenario == "structured":
        pts = []
        for x in np.linspace(6, 58, 27):
            pts.append([x, -8.0 + rng.normal(0, 0.18)])
            pts.append([x, 8.0 + rng.normal(0, 0.18)])
        for _ in range(50):
            pts.append([rng.uniform(4, 62), rng.choice([-1, 1]) * rng.uniform(10, 18)])
        return np.asarray(pts, dtype=np.float64)
    if scenario == "tunnel":
        pts = []
        for x in np.linspace(4, 70, 34):
            pts.append([x, -5.0 + rng.normal(0, 0.05)])
            pts.append([x, 5.0 + rng.normal(0, 0.05)])
        return np.asarray(pts, dtype=np.float64)
    raise ValueError(f"unknown scenario: {scenario}")


def body_pose_at_frame(frame_idx: int, frame_period: float, v_body: np.ndarray, omega: float) -> tuple[np.ndarray, float]:
    t = frame_idx * frame_period
    theta = omega * t
    if abs(omega) < 1e-9:
        pos = np.array([v_body[0] * t, v_body[1] * t], dtype=np.float64)
    else:
        pos = integrate_body_velocity(v_body, omega, t)
    return pos, theta


def render_sequence(
    scenario: str,
    frames: int,
    beams: int,
    bins: int,
    range_res: float,
    frame_period: float,
    beta: float,
    seed: int,
) -> dict:
    rng = np.random.default_rng(seed)
    if scenario == "structured":
        v_body = np.array([5.8, 0.18], dtype=np.float64)
        omega = 0.028
    else:
        v_body = np.array([6.2, 0.06], dtype=np.float64)
        omega = 0.006
    landmarks = make_landmarks(scenario, rng)
    azimuths = np.linspace(-np.pi, np.pi, beams, endpoint=False)
    ranges = (np.arange(bins, dtype=np.float64) + 0.5) * range_res
    scans = []
    poses = []
    beam_sigma = (2.0 * np.pi / beams) * 0.42
    range_sigma_bins = 1.15
    beam_times = np.linspace(0.0, frame_period, beams, endpoint=False)
    chirps = np.where(np.arange(beams) % 2 == 0, 1.0, -1.0)

    for k in range(frames):
        frame_start_pos, frame_start_theta = body_pose_at_frame(k, frame_period, v_body, omega)
        poses.append([k * frame_period, frame_start_pos[0], frame_start_pos[1], frame_start_theta])
        scan = np.zeros((beams, bins), dtype=np.float32)
        for i, alpha in enumerate(azimuths):
            dt = beam_times[i]
            theta = frame_start_theta + omega * dt
            pos = frame_start_pos + rot2(frame_start_theta) @ integrate_body_velocity(v_body, omega, dt)
            r_world_body = rot2(theta).T
            rel = (landmarks - pos) @ r_world_body
            r = np.linalg.norm(rel, axis=1)
            bearing = np.arctan2(rel[:, 1], rel[:, 0])
            bearing_err = np.arctan2(np.sin(bearing - alpha), np.cos(bearing - alpha))
            mask = (r > 1.0) & (r < ranges[-1] - 1.0) & (np.abs(bearing_err) < 3.0 * beam_sigma)
            if not np.any(mask):
                continue
            radial = np.cos(alpha) * v_body[0] + np.sin(alpha) * v_body[1]
            measured_r = r[mask] - chirps[i] * 0.5 * beta * radial
            bins_float = measured_r / range_res - 0.5
            weights = np.exp(-0.5 * (bearing_err[mask] / beam_sigma) ** 2)
            for bf, w in zip(bins_float, weights):
                center = int(round(bf))
                lo = max(0, center - 4)
                hi = min(bins, center + 5)
                idx = np.arange(lo, hi)
                scan[i, lo:hi] += (w * np.exp(-0.5 * ((idx - bf) / range_sigma_bins) ** 2)).astype(np.float32)
        scan += rng.normal(0.0, 0.015, size=scan.shape).astype(np.float32)
        scan[scan < 0] = 0
        row_max = scan.max(axis=1, keepdims=True)
        scan = np.divide(scan, np.maximum(row_max, 1e-6), out=np.zeros_like(scan), where=row_max > 0)
        scans.append(scan)

    return {
        "metadata": {
            "scenario": scenario,
            "frames": frames,
            "beams": beams,
            "bins": bins,
            "range_res": range_res,
            "frame_period": frame_period,
            "beta": beta,
            "omega": omega,
            "v_body": v_body.tolist(),
            "seed": seed,
        },
        "azimuths": azimuths.astype(np.float32),
        "ranges": ranges.astype(np.float32),
        "beam_times": beam_times.astype(np.float32),
        "chirps": chirps.astype(np.float32),
        "poses": np.asarray(poses, dtype=np.float64),
        "scans": np.stack(scans, axis=0),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/synthetic_dro.npz")
    parser.add_argument("--frames", type=int, default=48)
    parser.add_argument("--beams", type=int, default=180)
    parser.add_argument("--bins", type=int, default=220)
    parser.add_argument("--range-res", type=float, default=0.35)
    parser.add_argument("--frame-period", type=float, default=0.25)
    parser.add_argument("--beta", type=float, default=0.18)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = {
        name: render_sequence(
            name,
            args.frames,
            args.beams,
            args.bins,
            args.range_res,
            args.frame_period,
            args.beta,
            args.seed + offset,
        )
        for offset, name in enumerate(["structured", "tunnel"])
    }
    arrays = {}
    manifest = {}
    for name, seq in data.items():
        manifest[name] = seq["metadata"]
        for key, value in seq.items():
            if key != "metadata":
                arrays[f"{name}_{key}"] = value
    arrays["manifest_json"] = np.array(json.dumps(manifest, indent=2))
    np.savez_compressed(out, **arrays)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
