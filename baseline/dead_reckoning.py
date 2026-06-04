"""Simple baseline: fixed forward velocity with gyroscope integration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def rot2(theta: float) -> np.ndarray:
    c = np.cos(theta)
    s = np.sin(theta)
    return np.array([[c, -s], [s, c]], dtype=np.float64)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/synthetic_dro.npz")
    parser.add_argument("--output-dir", default="checkpoints/baseline")
    args = parser.parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset = np.load(args.data, allow_pickle=False)
    manifest = json.loads(str(dataset["manifest_json"].item()))
    results = {}
    for scenario in ["structured", "tunnel"]:
        gt = dataset[f"{scenario}_poses"]
        meta = manifest[scenario]
        gyro_yaw = dataset[f"{scenario}_gyro_yaw"]
        frame_period = float(meta["frame_period"])
        v = np.array([4.5, 0.0], dtype=np.float64)
        pose = np.array([gt[0, 1], gt[0, 2], gt[0, 3]], dtype=np.float64)
        traj = [[0.0, pose[0], pose[1], pose[2], v[0], v[1]]]
        for k in range(1, len(gt)):
            omega = float(gyro_yaw[k])
            pose[:2] += rot2(pose[2]) @ (v * frame_period)
            pose[2] += omega * frame_period
            traj.append([k * frame_period, pose[0], pose[1], pose[2], v[0], v[1]])
        results[scenario] = {"trajectory": traj, "ground_truth": gt.tolist()}
    with (out_dir / "dead_reckoning_predictions.json").open("w") as f:
        json.dump({"method": "dead_reckoning", "scenarios": results}, f, indent=2)
    print(out_dir / "dead_reckoning_predictions.json")


if __name__ == "__main__":
    main()
