"""Held-out test-slice scorer for odometry prediction artifacts.

This evaluator mirrors the train-slice prediction JSON contract but scores only
the odd-indexed frames from each scenario. When a train score file is available,
it filters and validates the test report so every experiment contains exactly
the same method keys as the visible train report.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


SLICE_NAME = "test"
FRAME_OFFSET = 1
DEFAULT_DATA_PATH = Path("data/synthetic_dro.npz")


def wrap_angle(x: np.ndarray) -> np.ndarray:
    return np.arctan2(np.sin(x), np.cos(x))


def frame_slice(values: np.ndarray) -> np.ndarray:
    return values[FRAME_OFFSET::2]


def segment_metrics(pred: np.ndarray, gt: np.ndarray, step: int = 4) -> tuple[float, float, float, float, float]:
    n = min(len(pred), len(gt))
    pred = pred[:n]
    gt = gt[:n]
    if n < 3:
        raise ValueError("at least three sliced frames are required for odometry scoring")

    distances = np.zeros(n)
    distances[1:] = np.cumsum(np.linalg.norm(np.diff(gt[:, 1:3], axis=0), axis=1))
    pred_distances = np.zeros(n)
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
            rot_delta = pred[j, 3] - pred[i, 3] - (gt[j, 3] - gt[i, 3])
            rot_err.append(abs(np.degrees(wrap_angle(np.array([rot_delta]))[0])) / (length / 100.0))

    if not trans_err:
        raise ValueError("sliced trajectory is too short for the configured segment lengths")

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


def canonical_method_name(method: str) -> str:
    if method == "dead_reckoning":
        return "fixed_velocity_gyro"
    return method


def load_ground_truth(data_path: Path) -> dict[str, np.ndarray]:
    dataset = np.load(data_path, allow_pickle=False)
    return {
        key.removesuffix("_poses"): np.asarray(dataset[key], dtype=np.float64)
        for key in dataset.files
        if key.endswith("_poses")
    }


def score_file(
    path: Path,
    ground_truth: dict[str, np.ndarray],
) -> tuple[str, dict[str, dict[str, float]], dict[str, float]]:
    with path.open() as f:
        artifact = json.load(f)

    method = canonical_method_name(artifact["method"])
    scenario_scores = {}
    for scenario, seq in artifact["scenarios"].items():
        if scenario not in ground_truth:
            raise ValueError(f"{path} contains unknown scenario {scenario!r}")
        pred = frame_slice(np.asarray(seq["trajectory"], dtype=np.float64))
        gt = frame_slice(ground_truth[scenario])
        te, re, ve, ee, pe = segment_metrics(pred, gt)
        scenario_scores[scenario] = {
            "translation_error_pct": te,
            "rotation_error_deg_per_100m": re,
            "velocity_rmse_mps": ve,
            "endpoint_position_error_m": ee,
            "path_length_error_pct": pe,
        }

    if not scenario_scores:
        raise ValueError(f"{path} does not contain any scenarios")

    avg_te = float(np.mean([v["translation_error_pct"] for v in scenario_scores.values()]))
    avg_re = float(np.mean([v["rotation_error_deg_per_100m"] for v in scenario_scores.values()]))
    averages = {
        "avg_translation_error_pct": avg_te,
        "avg_rotation_error_deg_per_100m": avg_re,
        "velocity_rmse_mps": float(np.mean([v["velocity_rmse_mps"] for v in scenario_scores.values()])),
        "endpoint_position_error_m": float(np.mean([v["endpoint_position_error_m"] for v in scenario_scores.values()])),
        "path_length_error_pct": float(np.mean([v["path_length_error_pct"] for v in scenario_scores.values()])),
    }
    return method, scenario_scores, averages


def build_scores(prediction_paths: list[Path], data_path: Path) -> dict[str, Any]:
    ground_truth = load_ground_truth(data_path)
    results_main = {}
    results_ablation = {}
    scenario_results: dict[str, dict[str, dict[str, float]]] = {}

    for pred_path in prediction_paths:
        method, scenario_scores, averages = score_file(pred_path, ground_truth)
        if method in results_main:
            raise ValueError(f"duplicate prediction artifact for method {method!r}")

        results_main[method] = {
            "avg_translation_error_pct": averages["avg_translation_error_pct"],
            "avg_rotation_error_deg_per_100m": averages["avg_rotation_error_deg_per_100m"],
            "endpoint_position_error_m": averages["endpoint_position_error_m"],
            "path_length_error_pct": averages["path_length_error_pct"],
        }
        if method != "fixed_velocity_gyro":
            results_ablation[method] = {
                "avg_translation_error_pct": averages["avg_translation_error_pct"],
                "avg_rotation_error_deg_per_100m": averages["avg_rotation_error_deg_per_100m"],
                "velocity_rmse_mps": averages["velocity_rmse_mps"],
                "endpoint_position_error_m": averages["endpoint_position_error_m"],
                "path_length_error_pct": averages["path_length_error_pct"],
            }
        for scenario, metrics in scenario_scores.items():
            scenario_results.setdefault(scenario, {})[method] = {
                "translation_error_pct": metrics["translation_error_pct"],
                "rotation_error_deg_per_100m": metrics["rotation_error_deg_per_100m"],
                "endpoint_position_error_m": metrics["endpoint_position_error_m"],
                "path_length_error_pct": metrics["path_length_error_pct"],
            }

    return {
        "_metadata": {
            "slice": SLICE_NAME,
            "split": "odd_frame_indices",
            "ground_truth_data": str(data_path),
            "prediction_files": [str(path) for path in prediction_paths],
        },
        "experiments": {
            "synthetic_doppler_core": {"results": results_main},
            "synthetic_doppler_structured": {"results": scenario_results.get("structured", {})},
            "synthetic_doppler_tunnel": {"results": scenario_results.get("tunnel", {})},
            "synthetic_doppler_ablation": {"results": results_ablation},
        },
    }


def experiment_results(scores: dict[str, Any]) -> dict[str, dict[str, Any]]:
    experiments = scores.get("experiments", {})
    return {
        exp_name: exp_data.get("results", {})
        for exp_name, exp_data in experiments.items()
        if isinstance(exp_data, dict)
    }


def match_train_methods(scores: dict[str, Any], train_scores_path: Path) -> dict[str, Any]:
    if not train_scores_path.exists():
        return scores

    with train_scores_path.open() as f:
        train_scores = json.load(f)

    train_results = experiment_results(train_scores)
    test_experiments = scores["experiments"]
    for exp_name, expected_results in train_results.items():
        if exp_name not in test_experiments:
            raise ValueError(f"test scores are missing train experiment {exp_name!r}")

        actual_results = test_experiments[exp_name].get("results", {})
        missing = [method for method in expected_results if method not in actual_results]
        if missing:
            missing_list = ", ".join(missing)
            raise ValueError(f"test predictions are missing train-scored methods for {exp_name}: {missing_list}")

        test_experiments[exp_name]["results"] = {
            method: actual_results[method] for method in expected_results
        }

    scores["_metadata"]["matched_train_scores"] = str(train_scores_path)
    return scores


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", nargs="+", required=True)
    parser.add_argument("--output", default="scoring/scores_test.json")
    parser.add_argument("--match-train", default="scoring/scores_train.json")
    parser.add_argument("--data", default=str(DEFAULT_DATA_PATH))
    args = parser.parse_args()

    prediction_paths = [Path(path) for path in args.predictions]
    scores = build_scores(prediction_paths, Path(args.data))
    scores = match_train_methods(scores, Path(args.match_train))

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        json.dump(scores, f, indent=2)
    print(json.dumps(scores, indent=2))


if __name__ == "__main__":
    main()
