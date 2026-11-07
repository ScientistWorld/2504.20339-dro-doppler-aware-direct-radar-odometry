"""Visible train-split scorer for radar odometry prediction artifacts.

Scores every prediction artifact passed on the command line against the
labelled training sequences in data/train.npz. The scoring rules match the
held-out evaluator so a method behaves the same way on both splits:

* comparator rows (fixed-velocity dead reckoning and two reference variants)
  come from frozen predictions in eval/train/comparators/;
* from a method artifact only the per-frame trajectory rows are used and all
  metrics are recomputed from them;
* malformed, incomplete, non-finite or physically impossible output,
  duplicate method names, or a result no better than dead reckoning marks
  the method as failed, with every metric at its ceiling value.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
COMPARATOR_DIR = HERE / "comparators"
DEFAULT_DATA = Path("data/train.npz")
SLICE_NAME = "train"

SEGMENT_LENGTHS_M = (20.0, 35.0, 50.0)
SEGMENT_STEP = 2
TIME_TOLERANCE_S = 1e-3
MAX_ABS_POSITION_M = 1e5
MAX_SPEED_MPS = 100.0
CEILING = {
    "translation_error_pct": 100.0,
    "rotation_error_deg_per_100m": 100.0,
    "velocity_rmse_mps": 10.0,
    "endpoint_position_error_m": 100.0,
    "path_length_error_pct": 100.0,
}
BASELINE_ROW = "fixed_velocity_gyro"
RESERVED_NAMES = {"fixed_velocity_gyro", "dead_reckoning", "dro_d", "dro_g"}
NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")
METRIC_KEYS = (
    "translation_error_pct",
    "rotation_error_deg_per_100m",
    "endpoint_position_error_m",
    "path_length_error_pct",
)


class InvalidPrediction(Exception):
    pass


def load_train_labels(data_path: Path) -> dict[str, dict[str, Any]]:
    with np.load(data_path, allow_pickle=False) as data:
        manifest = json.loads(str(data["manifest_json"].item()))
        labels = {}
        for name, info in manifest["sequences"].items():
            poses = np.asarray(data[f"{name}_poses"], dtype=np.float64)
            labels[name] = {
                "scenario": info["scenario"],
                "frame_times": poses[:, 0].copy(),
                "poses": poses[:, 1:4].copy(),
                "velocities": np.asarray(data[f"{name}_velocities"], dtype=np.float64),
            }
    return labels


def wrap(x):
    return np.arctan2(np.sin(x), np.cos(x))


def to_body(theta: float, vec: np.ndarray) -> np.ndarray:
    c = np.cos(theta)
    s = np.sin(theta)
    return np.array([c * vec[0] + s * vec[1], -s * vec[0] + c * vec[1]])


def check_rows(raw: Any, frame_times: np.ndarray) -> np.ndarray:
    if not isinstance(raw, list):
        raise InvalidPrediction("trajectory is not a list")
    if len(raw) != len(frame_times):
        raise InvalidPrediction(f"trajectory has {len(raw)} rows, expected one per frame ({len(frame_times)})")
    for row in raw:
        if not isinstance(row, (list, tuple)) or len(row) != 6:
            raise InvalidPrediction("each row must be [t, x, y, heading, vx_body, vy_body]")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in row):
            raise InvalidPrediction("trajectory rows must contain only numbers")
    traj = np.asarray(raw, dtype=np.float64)
    if not np.isfinite(traj).all():
        raise InvalidPrediction("trajectory contains non-finite values")
    if np.abs(traj[:, 0] - frame_times).max() > TIME_TOLERANCE_S:
        raise InvalidPrediction("timestamps do not match the scan start times")
    if np.abs(traj[:, 1:3]).max() > MAX_ABS_POSITION_M:
        raise InvalidPrediction("positions are physically impossible")
    if np.hypot(traj[:, 4], traj[:, 5]).max() > MAX_SPEED_MPS:
        raise InvalidPrediction("velocities are physically impossible")
    return traj


def kitti_style_errors(traj: np.ndarray, label: dict[str, Any]) -> dict[str, float]:
    gt = label["poses"]
    steps = np.linalg.norm(np.diff(gt[:, :2], axis=0), axis=1)
    travelled = np.concatenate([[0.0], np.cumsum(steps)])
    n = len(gt)
    t_errs = []
    r_errs = []
    for start in range(0, n - 1, SEGMENT_STEP):
        for seg in SEGMENT_LENGTHS_M:
            end = int(np.searchsorted(travelled, travelled[start] + seg))
            if end >= n:
                continue
            gt_rel = to_body(gt[start, 2], gt[end, :2] - gt[start, :2])
            pr_rel = to_body(traj[start, 3], traj[end, 1:3] - traj[start, 1:3])
            t_errs.append(100.0 * float(np.hypot(*(pr_rel - gt_rel))) / seg)
            heading_err = wrap((traj[end, 3] - traj[start, 3]) - (gt[end, 2] - gt[start, 2]))
            r_errs.append(abs(float(np.degrees(heading_err))) * 100.0 / seg)
    if not t_errs:
        raise RuntimeError("train labels are too short for the configured segment lengths")
    gt_end = to_body(gt[0, 2], gt[-1, :2] - gt[0, :2])
    pr_end = to_body(traj[0, 3], traj[-1, 1:3] - traj[0, 1:3])
    pred_length = float(np.linalg.norm(np.diff(traj[:, 1:3], axis=0), axis=1).sum())
    gt_length = float(travelled[-1])
    dv = traj[:, 4:6] - label["velocities"]
    values = {
        "translation_error_pct": float(np.mean(t_errs)),
        "rotation_error_deg_per_100m": float(np.mean(r_errs)),
        "velocity_rmse_mps": float(np.sqrt(np.mean(dv[:, 0] ** 2 + dv[:, 1] ** 2))),
        "endpoint_position_error_m": float(np.hypot(*(pr_end - gt_end))),
        "path_length_error_pct": 100.0 * abs(pred_length - gt_length) / max(gt_length, 1e-6),
    }
    return {k: min(v, CEILING[k]) for k, v in values.items()}


def score_artifact_sequences(sequences: Any, labels: dict[str, dict[str, Any]]) -> dict[str, dict[str, float]]:
    if not isinstance(sequences, dict):
        raise InvalidPrediction("artifact has no 'sequences' mapping")
    out = {}
    for name in sorted(labels):
        entry = sequences.get(name)
        if not isinstance(entry, dict) or "trajectory" not in entry:
            raise InvalidPrediction(f"missing prediction for train sequence {name!r}")
        out[name] = kitti_style_errors(check_rows(entry["trajectory"], labels[name]["frame_times"]), labels[name])
    return out


def summarize(per_seq: dict[str, dict[str, float]], labels: dict[str, dict[str, Any]]) -> dict[str, dict[str, float]]:
    every = sorted(labels)

    def avg(key: str, members: list[str]) -> float:
        return float(np.mean([per_seq[m][key] for m in members]))

    core = {
        "avg_translation_error_pct": avg("translation_error_pct", every),
        "avg_rotation_error_deg_per_100m": avg("rotation_error_deg_per_100m", every),
        "endpoint_position_error_m": avg("endpoint_position_error_m", every),
        "path_length_error_pct": avg("path_length_error_pct", every),
    }
    summary = {"core": core, "ablation": {**core, "velocity_rmse_mps": avg("velocity_rmse_mps", every)}}
    for scenario in ("structured", "tunnel"):
        members = [m for m in every if labels[m]["scenario"] == scenario]
        summary[scenario] = {key: avg(key, members) for key in METRIC_KEYS}
    return summary


def failed_summary() -> dict[str, dict[str, float]]:
    core = {
        "avg_translation_error_pct": CEILING["translation_error_pct"],
        "avg_rotation_error_deg_per_100m": CEILING["rotation_error_deg_per_100m"],
        "endpoint_position_error_m": CEILING["endpoint_position_error_m"],
        "path_length_error_pct": CEILING["path_length_error_pct"],
    }
    per_scenario = {key: CEILING[key] for key in METRIC_KEYS}
    return {
        "core": core,
        "ablation": {**core, "velocity_rmse_mps": CEILING["velocity_rmse_mps"]},
        "structured": dict(per_scenario),
        "tunnel": dict(per_scenario),
    }


def method_name(path: Path, artifact: Any) -> str:
    if isinstance(artifact, dict) and isinstance(artifact.get("method"), str) and NAME_RE.match(artifact["method"]):
        return artifact["method"]
    stem = path.name.removesuffix(".json").removesuffix("_predictions")
    return re.sub(r"[^A-Za-z0-9_.\-]", "_", stem)[:64] or "unnamed"


def build_scores(prediction_paths: list[Path], data_path: Path) -> dict[str, Any]:
    labels = load_train_labels(data_path)
    rows: dict[str, dict[str, dict[str, float]]] = {}
    comparators = []
    for path in sorted(COMPARATOR_DIR.glob("*.json")):
        artifact = json.loads(path.read_text())
        rows[artifact["method"]] = summarize(score_artifact_sequences(artifact["sequences"], labels), labels)
        comparators.append(artifact["method"])
    if BASELINE_ROW not in rows:
        raise RuntimeError(f"missing frozen comparator {BASELINE_ROW!r} in {COMPARATOR_DIR}")
    baseline_te = rows[BASELINE_ROW]["core"]["avg_translation_error_pct"]

    ignored = []
    by_name: dict[str, list[tuple[Path, Any]]] = {}
    for path in prediction_paths:
        try:
            artifact = json.loads(path.read_text())
        except (OSError, ValueError):
            artifact = None
        name = method_name(path, artifact)
        if name.lower() in RESERVED_NAMES:
            ignored.append({"file": str(path), "reason": f"{name!r} is a fixed comparator row owned by the evaluator"})
            continue
        by_name.setdefault(name, []).append((path, artifact))

    failures: dict[str, str] = {}
    methods = sorted(by_name)
    for name in methods:
        entries = by_name[name]
        problem = None
        summary = None
        if len(entries) != 1:
            problem = "several artifacts claim this method name: " + ", ".join(str(p) for p, _ in entries)
        elif not isinstance(entries[0][1], dict):
            problem = "artifact is not a JSON object"
        else:
            try:
                summary = summarize(score_artifact_sequences(entries[0][1].get("sequences"), labels), labels)
            except InvalidPrediction as exc:
                problem = str(exc)
        if summary is not None and summary["core"]["avg_translation_error_pct"] >= baseline_te:
            problem = "average translation error is not better than fixed-velocity dead reckoning"
        if problem is not None:
            failures[name] = problem
            summary = failed_summary()
        rows[name] = summary

    names = comparators + methods
    return {
        "_metadata": {
            "slice": SLICE_NAME,
            "split": "visible labelled sequences in data/train.npz",
            "sequences": len(labels),
            "segment_lengths_m": list(SEGMENT_LENGTHS_M),
            "comparator_rows": comparators,
            "ground_truth_data": str(data_path),
            "prediction_files": [str(p) for p in prediction_paths],
            "ignored_artifacts": ignored,
            "failed_methods": failures,
            "ceilings": CEILING,
        },
        "experiments": {
            "synthetic_doppler_core": {"results": {n: rows[n]["core"] for n in names}},
            "synthetic_doppler_structured": {"results": {n: rows[n]["structured"] for n in names}},
            "synthetic_doppler_tunnel": {"results": {n: rows[n]["tunnel"] for n in names}},
            "synthetic_doppler_ablation": {"results": {n: rows[n]["ablation"] for n in names if n != BASELINE_ROW}},
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", nargs="*", default=[])
    parser.add_argument("--data", default=str(DEFAULT_DATA))
    parser.add_argument("--output", default="scoring/scores_train.json")
    args = parser.parse_args()
    scores = build_scores([Path(p) for p in args.predictions], Path(args.data))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(scores, indent=2, allow_nan=False)
    out.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
