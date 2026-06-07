"""Method-agnostic odometry scoring for prediction JSON artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def wrap_angle(x: np.ndarray) -> np.ndarray:
    return np.arctan2(np.sin(x), np.cos(x))


def segment_metrics(pred: np.ndarray, gt: np.ndarray, step: int = 4) -> tuple[float, float, float, float, float]:
    n = min(len(pred), len(gt))
    pred = pred[:n]
    gt = gt[:n]
    if n < 3:
        raise ValueError("at least three frames are required for odometry scoring")
    distances = np.zeros(n)
    if n > 1:
        distances[1:] = np.cumsum(np.linalg.norm(np.diff(gt[:, 1:3], axis=0), axis=1))
    pred_distances = np.zeros(n)
    if n > 1:
        pred_distances[1:] = np.cumsum(np.linalg.norm(np.diff(pred[:, 1:3], axis=0), axis=1))
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
    if not trans_err:
        raise ValueError("trajectory is too short for the configured segment lengths")
    dt = np.diff(gt[:, 0])
    if len(dt) > 0:
        world_velocity = np.diff(gt[:, 1:3], axis=0) / np.maximum(dt[:, None], 1e-6)
        heading = gt[:-1, 3]
        c = np.cos(heading)
        s = np.sin(heading)
        gt_body_velocity = np.stack(
            [
                c * world_velocity[:, 0] + s * world_velocity[:, 1],
                -s * world_velocity[:, 0] + c * world_velocity[:, 1],
            ],
            axis=1,
        )
        pred_body_velocity = pred[1 : len(gt_body_velocity) + 1, 4:6]
        vel_rmse = float(np.sqrt(np.mean((pred_body_velocity - gt_body_velocity) ** 2)))
    else:
        vel_rmse = 0.0
    endpoint_error = float(np.linalg.norm(pred[-1, 1:3] - gt[-1, 1:3]))
    path_length_error = float(
        100.0 * abs(pred_distances[-1] - distances[-1]) / max(distances[-1], 1e-6)
    )
    return float(np.mean(trans_err)), float(np.mean(rot_err)), vel_rmse, endpoint_error, path_length_error


def load_ground_truth(data_path: Path) -> dict[str, np.ndarray]:
    dataset = np.load(data_path, allow_pickle=False)
    return {
        key.removesuffix("_poses"): np.asarray(dataset[key], dtype=np.float64)
        for key in dataset.files
        if key.endswith("_poses")
    }


def score_file(path: Path, ground_truth: dict[str, np.ndarray]) -> dict:
    with path.open() as f:
        artifact = json.load(f)
    method = artifact["method"]
    scenario_scores = {}
    for scenario, seq in artifact["scenarios"].items():
        if scenario not in ground_truth:
            raise ValueError(f"{path} contains unknown scenario {scenario!r}")
        pred = np.asarray(seq["trajectory"], dtype=np.float64)
        gt = ground_truth[scenario]
        te, re, ve, ee, pe = segment_metrics(pred, gt)
        scenario_scores[scenario] = {
            "translation_error_pct": te,
            "rotation_error_deg_per_100m": re,
            "velocity_rmse_mps": ve,
            "endpoint_position_error_m": ee,
            "path_length_error_pct": pe,
        }
    avg_te = float(np.mean([v["translation_error_pct"] for v in scenario_scores.values()]))
    avg_re = float(np.mean([v["rotation_error_deg_per_100m"] for v in scenario_scores.values()]))
    avg_ve = float(np.mean([v["velocity_rmse_mps"] for v in scenario_scores.values()]))
    avg_ee = float(np.mean([v["endpoint_position_error_m"] for v in scenario_scores.values()]))
    avg_pe = float(np.mean([v["path_length_error_pct"] for v in scenario_scores.values()]))
    return method, scenario_scores, avg_te, avg_re, avg_ve, avg_ee, avg_pe


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", nargs="+", required=True)
    parser.add_argument("--data", default="data/synthetic_dro.npz")
    parser.add_argument("--output", default="scoring/scores.json")
    args = parser.parse_args()
    ground_truth = load_ground_truth(Path(args.data))
    results_main = {}
    results_ablation = {}
    scenario_results: dict[str, dict[str, dict[str, float]]] = {}
    for pred_path in args.predictions:
        method, scenario_scores, avg_te, avg_re, avg_ve, avg_ee, avg_pe = score_file(Path(pred_path), ground_truth)
        if method == "dead_reckoning":
            name = "fixed_velocity_gyro"
        else:
            name = method
        results_main[name] = {
            "avg_translation_error_pct": avg_te,
            "avg_rotation_error_deg_per_100m": avg_re,
            "endpoint_position_error_m": avg_ee,
            "path_length_error_pct": avg_pe,
        }
        for scenario, metrics in scenario_scores.items():
            scenario_results.setdefault(scenario, {})[name] = {
                "translation_error_pct": metrics["translation_error_pct"],
                "rotation_error_deg_per_100m": metrics["rotation_error_deg_per_100m"],
                "endpoint_position_error_m": metrics["endpoint_position_error_m"],
                "path_length_error_pct": metrics["path_length_error_pct"],
            }
        if name in {"dro_d", "dro_g", "dro_gd"}:
            results_ablation[name] = {
                "avg_translation_error_pct": avg_te,
                "avg_rotation_error_deg_per_100m": avg_re,
                "velocity_rmse_mps": avg_ve,
                "endpoint_position_error_m": avg_ee,
                "path_length_error_pct": avg_pe,
            }
    scores = {
        "experiments": {
            "synthetic_doppler_core": {"results": results_main},
            "synthetic_doppler_structured": {"results": scenario_results.get("structured", {})},
            "synthetic_doppler_tunnel": {"results": scenario_results.get("tunnel", {})},
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
