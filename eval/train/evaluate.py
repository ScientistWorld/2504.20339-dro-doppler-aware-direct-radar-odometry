"""Visible train-slice scorer for odometry prediction artifacts.

This evaluator mirrors the top-level prediction JSON contract but scores only
the even-indexed frames from each scenario. Future methods can optimize against
this slice without seeing the held-out odd-frame test slice.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


SLICE_NAME = "train"
FRAME_OFFSET = 0


def wrap_angle(x: np.ndarray) -> np.ndarray:
    return np.arctan2(np.sin(x), np.cos(x))


def frame_slice(values: np.ndarray) -> np.ndarray:
    return values[FRAME_OFFSET::2]


def segment_metrics(pred: np.ndarray, gt: np.ndarray, step: int = 4) -> tuple[float, float, float]:
    n = min(len(pred), len(gt))
    pred = pred[:n]
    gt = gt[:n]
    if n < 3:
        raise ValueError("at least three sliced frames are required for odometry scoring")

    distances = np.zeros(n)
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

    return float(np.mean(trans_err)), float(np.mean(rot_err)), vel_rmse


def canonical_method_name(method: str) -> str:
    if method == "dead_reckoning":
        return "fixed_velocity_gyro"
    return method


def score_file(path: Path) -> tuple[str, dict[str, dict[str, float]], float, float, float]:
    with path.open() as f:
        artifact = json.load(f)

    method = canonical_method_name(artifact["method"])
    scenario_scores = {}
    for scenario, seq in artifact["scenarios"].items():
        pred = frame_slice(np.asarray(seq["trajectory"], dtype=np.float64))
        gt = frame_slice(np.asarray(seq["ground_truth"], dtype=np.float64))
        te, re, ve = segment_metrics(pred, gt)
        scenario_scores[scenario] = {
            "translation_error_pct": te,
            "rotation_error_deg_per_100m": re,
            "velocity_rmse_mps": ve,
        }

    if not scenario_scores:
        raise ValueError(f"{path} does not contain any scenarios")

    avg_te = float(np.mean([v["translation_error_pct"] for v in scenario_scores.values()]))
    avg_re = float(np.mean([v["rotation_error_deg_per_100m"] for v in scenario_scores.values()]))
    avg_ve = float(np.mean([v["velocity_rmse_mps"] for v in scenario_scores.values()]))
    return method, scenario_scores, avg_te, avg_re, avg_ve


def build_scores(prediction_paths: list[Path]) -> dict[str, Any]:
    results_main = {}
    results_ablation = {}
    scenario_results: dict[str, dict[str, dict[str, float]]] = {}

    for pred_path in prediction_paths:
        method, scenario_scores, avg_te, avg_re, avg_ve = score_file(pred_path)
        if method in results_main:
            raise ValueError(f"duplicate prediction artifact for method {method!r}")

        results_main[method] = {
            "avg_translation_error_pct": avg_te,
            "avg_rotation_error_deg_per_100m": avg_re,
        }
        if method != "fixed_velocity_gyro":
            results_ablation[method] = {
                "avg_translation_error_pct": avg_te,
                "avg_rotation_error_deg_per_100m": avg_re,
                "velocity_rmse_mps": avg_ve,
            }
        for scenario, metrics in scenario_scores.items():
            scenario_results.setdefault(scenario, {})[method] = {
                "translation_error_pct": metrics["translation_error_pct"],
                "rotation_error_deg_per_100m": metrics["rotation_error_deg_per_100m"],
            }

    return {
        "_metadata": {
            "slice": SLICE_NAME,
            "split": "even_frame_indices",
            "prediction_files": [str(path) for path in prediction_paths],
        },
        "experiments": {
            "synthetic_doppler_core": {"results": results_main},
            "synthetic_doppler_structured": {"results": scenario_results.get("structured", {})},
            "synthetic_doppler_tunnel": {"results": scenario_results.get("tunnel", {})},
            "synthetic_doppler_ablation": {"results": results_ablation},
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", nargs="+", required=True)
    parser.add_argument("--output", default="scoring/scores_train.json")
    args = parser.parse_args()

    prediction_paths = [Path(path) for path in args.predictions]
    scores = build_scores(prediction_paths)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        json.dump(scores, f, indent=2)
    print(json.dumps(scores, indent=2))


if __name__ == "__main__":
    main()
