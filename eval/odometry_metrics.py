"""Method-agnostic odometry scoring for prediction JSON artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def wrap_angle(x: np.ndarray) -> np.ndarray:
    return np.arctan2(np.sin(x), np.cos(x))


def segment_metrics(pred: np.ndarray, gt: np.ndarray, step: int = 4) -> tuple[float, float, float]:
    n = min(len(pred), len(gt))
    pred = pred[:n]
    gt = gt[:n]
    distances = np.zeros(n)
    if n > 1:
        distances[1:] = np.cumsum(np.linalg.norm(np.diff(gt[:, 1:3], axis=0), axis=1))
    segment_lengths = [20.0, 35.0, 50.0]
    trans_err = []
    rot_err = []
    for i in range(0, n - 2, step):
        for length in segment_lengths:
            j = int(np.searchsorted(distances, distances[i] + length))
            if j >= n:
                continue
            gt_delta = gt[j, 1:3] - gt[i, 1:3]
            pr_delta = pred[j, 1:3] - pred[i, 1:3]
            trans_err.append(100.0 * np.linalg.norm(pr_delta - gt_delta) / max(np.linalg.norm(gt_delta), 1e-6))
            rot_err.append(abs(np.degrees(wrap_angle(np.array([pred[j, 3] - pred[i, 3] - (gt[j, 3] - gt[i, 3])]))[0])) / (length / 100.0))
    pred_v = pred[:, 4:6]
    gt_dt = np.maximum(np.diff(gt[:, 0], prepend=gt[0, 0]), 1e-6)
    gt_speed = np.linalg.norm(np.diff(gt[:, 1:3], axis=0, prepend=gt[[0], 1:3]), axis=1) / gt_dt
    vel_rmse = float(np.sqrt(np.mean((np.linalg.norm(pred_v, axis=1) - gt_speed) ** 2)))
    return float(np.mean(trans_err)), float(np.mean(rot_err)), vel_rmse


def score_file(path: Path) -> dict:
    with path.open() as f:
        artifact = json.load(f)
    method = artifact["method"]
    scenario_scores = {}
    for scenario, seq in artifact["scenarios"].items():
        pred = np.asarray(seq["trajectory"], dtype=np.float64)
        gt = np.asarray(seq["ground_truth"], dtype=np.float64)
        te, re, ve = segment_metrics(pred, gt)
        scenario_scores[scenario] = {
            "translation_error_pct": te,
            "rotation_error_deg_per_100m": re,
            "velocity_rmse_mps": ve,
        }
    avg_te = float(np.mean([v["translation_error_pct"] for v in scenario_scores.values()]))
    avg_re = float(np.mean([v["rotation_error_deg_per_100m"] for v in scenario_scores.values()]))
    avg_ve = float(np.mean([v["velocity_rmse_mps"] for v in scenario_scores.values()]))
    return method, scenario_scores, avg_te, avg_re, avg_ve


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", nargs="+", required=True)
    parser.add_argument("--output", default="scoring/scores.json")
    args = parser.parse_args()
    results_main = {}
    results_ablation = {}
    for pred_path in args.predictions:
        method, scenario_scores, avg_te, avg_re, avg_ve = score_file(Path(pred_path))
        if method == "dead_reckoning":
            name = "fixed_velocity_gyro"
        else:
            name = method
        results_main[name] = {
            "avg_translation_error_pct": avg_te,
            "avg_rotation_error_deg_per_100m": avg_re,
        }
        if name == "dro_gd":
            results_ablation[name] = {
                "avg_translation_error_pct": avg_te,
                "avg_rotation_error_deg_per_100m": avg_re,
                "velocity_rmse_mps": avg_ve,
            }
    scores = {
        "experiments": {
            "synthetic_doppler_core": {"results": results_main},
            "synthetic_doppler_ablation": {"results": results_ablation},
        }
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        json.dump(scores, f, indent=2)
    print(json.dumps(scores, indent=2))


if __name__ == "__main__":
    main()
