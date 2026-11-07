"""Simple comparator: fixed forward velocity with raw gyroscope integration.

Writes the fixed-velocity dead-reckoning trajectory for every sequence in the
given input files. The evaluators score this comparator from frozen copies in
eval/<split>/comparators/, so its row cannot be changed by a method.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

FORWARD_SPEED_MPS = 4.5


def rot2(theta: float) -> np.ndarray:
    c = np.cos(theta)
    s = np.sin(theta)
    return np.array([[c, -s], [s, c]], dtype=np.float64)


def arc(v: np.ndarray, omega: float, dt: float) -> np.ndarray:
    if abs(omega) < 1e-9:
        return v * dt
    s = np.sin(omega * dt)
    c = np.cos(omega * dt)
    return np.array([(s * v[0] - (1.0 - c) * v[1]) / omega, ((1.0 - c) * v[0] + s * v[1]) / omega])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", nargs="+", default=["data/train.npz", "data/test_inputs.npz"])
    parser.add_argument("--output", default="checkpoints/comparators/fixed_velocity_gyro_comparator.json")
    args = parser.parse_args()
    results = {}
    for path in args.inputs:
        with np.load(path, allow_pickle=False) as data:
            manifest = json.loads(str(data["manifest_json"].item()))
            period = float(manifest["sensor"]["frame_period"])
            for name in sorted(manifest["sequences"]):
                gyro = np.asarray(data[f"{name}_gyro_yaw"], dtype=np.float64)
                times = np.asarray(data[f"{name}_frame_times"], dtype=np.float64)
                v = np.array([FORWARD_SPEED_MPS, 0.0])
                pose = np.zeros(3)
                traj = []
                for k in range(len(times)):
                    traj.append([float(times[k]), float(pose[0]), float(pose[1]), float(pose[2]), float(v[0]), float(v[1])])
                    pose[:2] += rot2(pose[2]) @ arc(v, float(gyro[k]), period)
                    pose[2] += float(gyro[k]) * period
                results[name] = {"trajectory": traj}
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"method": "fixed_velocity_gyro", "sequences": results}, indent=1))
    print(out)


if __name__ == "__main__":
    main()
