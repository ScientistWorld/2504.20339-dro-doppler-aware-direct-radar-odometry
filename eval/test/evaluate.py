"""Held-out test scorer for radar odometry prediction artifacts.

Scores every prediction artifact passed on the command line against the
held-out test labels that live only in this directory. Everything on the
comparison side is owned here:

* ground truth: eval/test/test_labels.json (never read from data/);
* comparator rows (fixed-velocity dead reckoning and two reference
  variants): frozen predictions in eval/test/comparators/;
* test size, frame times, segment lengths and score ceilings: constants below.

From a method artifact only the per-frame trajectory rows are used; every
scored number is recomputed from them. Any malformed, incomplete, non-finite
or physically impossible output, modified test inputs, duplicate method
names, or a result no better than dead reckoning marks the method as failed:
all its metrics are set to the ceiling values (worst possible score).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
LABELS_PATH = HERE / "test_labels.json"
COMPARATOR_DIR = HERE / "comparators"
DEFAULT_INPUTS = Path("data/test_inputs.npz")
SLICE_NAME = "test"

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


class InvalidPrediction(Exception):
    pass


def inputs_digest(path: Path) -> str:
    h = hashlib.sha256()
    with np.load(path, allow_pickle=False) as data:
        for key in sorted(data.files):
            arr = np.ascontiguousarray(data[key])
            h.update(key.encode())
            h.update(str(arr.dtype).encode())
            h.update(str(arr.shape).encode())
            h.update(arr.tobytes())
    return h.hexdigest()


def load_labels() -> tuple[str, dict[str, dict[str, Any]]]:
    raw = json.loads(LABELS_PATH.read_text())
    labels = {}
    for name, seq in raw["sequences"].items():
        labels[name] = {
            "scenario": seq["scenario"],
            "frame_times": np.asarray(seq["frame_times"], dtype=np.float64),
            "poses": np.asarray(seq["poses"], dtype=np.float64),
            "velocities": np.asarray(seq["velocities"], dtype=np.float64),
        }
    return raw["inputs_sha256"], labels


def wrap_angle(x):
    return (np.asarray(x) + np.pi) % (2.0 * np.pi) - np.pi


def rot_t(theta: float) -> np.ndarray:
    c = np.cos(theta)
    s = np.sin(theta)
    return np.array([[c, s], [-s, c]])


def parse_trajectory(raw: Any, frame_times: np.ndarray) -> np.ndarray:
    n = len(frame_times)
    if not isinstance(raw, list):
        raise InvalidPrediction("trajectory is not a list")
    if len(raw) != n:
        raise InvalidPrediction(f"trajectory has {len(raw)} rows, expected one per frame ({n})")
    for row in raw:
        if not isinstance(row, (list, tuple)) or len(row) != 6:
            raise InvalidPrediction("each row must be [t, x, y, heading, vx_body, vy_body]")
        for value in row:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise InvalidPrediction("trajectory rows must contain only numbers")
    arr = np.asarray(raw, dtype=np.float64)
    if not np.all(np.isfinite(arr)):
        raise InvalidPrediction("trajectory contains non-finite values")
    if np.max(np.abs(arr[:, 0] - frame_times)) > TIME_TOLERANCE_S:
        raise InvalidPrediction("timestamps do not match the scan start times")
    if np.max(np.abs(arr[:, 1:3])) > MAX_ABS_POSITION_M:
        raise InvalidPrediction("positions are physically impossible")
    if np.max(np.hypot(arr[:, 4], arr[:, 5])) > MAX_SPEED_MPS:
        raise InvalidPrediction("velocities are physically impossible")
    return arr


def sequence_metrics(pred: np.ndarray, label: dict[str, Any]) -> dict[str, float]:
    gt_xy = label["poses"][:, 0:2]
    gt_th = label["poses"][:, 2]
    pr_xy = pred[:, 1:3]
    pr_th = pred[:, 3]
    n = len(gt_xy)
    dist = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(gt_xy, axis=0), axis=1))])

    trans_err = []
    rot_err = []
    for i in range(0, n - 1, SEGMENT_STEP):
        for length in SEGMENT_LENGTHS_M:
            j = int(np.searchsorted(dist, dist[i] + length))
            if j >= n:
                continue
            d_gt = rot_t(gt_th[i]) @ (gt_xy[j] - gt_xy[i])
            d_pr = rot_t(pr_th[i]) @ (pr_xy[j] - pr_xy[i])
            trans_err.append(100.0 * float(np.linalg.norm(d_pr - d_gt)) / length)
            d_phi = wrap_angle((pr_th[j] - pr_th[i]) - (gt_th[j] - gt_th[i]))
            rot_err.append(float(np.degrees(abs(d_phi))) / (length / 100.0))
    if not trans_err:
        raise RuntimeError("test labels are too short for the configured segment lengths")

    end_gt = rot_t(gt_th[0]) @ (gt_xy[-1] - gt_xy[0])
    end_pr = rot_t(pr_th[0]) @ (pr_xy[-1] - pr_xy[0])
    path_gt = float(dist[-1])
    path_pr = float(np.sum(np.linalg.norm(np.diff(pr_xy, axis=0), axis=1)))
    vel_err = pred[:, 4:6] - label["velocities"]
    metrics = {
        "translation_error_pct": float(np.mean(trans_err)),
        "rotation_error_deg_per_100m": float(np.mean(rot_err)),
        "velocity_rmse_mps": float(np.sqrt(np.mean(np.sum(vel_err**2, axis=1)))),
        "endpoint_position_error_m": float(np.linalg.norm(end_pr - end_gt)),
        "path_length_error_pct": 100.0 * abs(path_pr - path_gt) / max(path_gt, 1e-6),
    }
    return {key: min(value, CEILING[key]) for key, value in metrics.items()}


def score_sequences(sequences: Any, labels: dict[str, dict[str, Any]]) -> dict[str, dict[str, float]]:
    if not isinstance(sequences, dict):
        raise InvalidPrediction("artifact has no 'sequences' mapping")
    per_sequence = {}
    for name, label in labels.items():
        entry = sequences.get(name)
        if not isinstance(entry, dict) or "trajectory" not in entry:
            raise InvalidPrediction(f"missing prediction for test sequence {name!r}")
        pred = parse_trajectory(entry["trajectory"], label["frame_times"])
        per_sequence[name] = sequence_metrics(pred, label)
    return per_sequence


def aggregate(per_sequence: dict[str, dict[str, float]], labels: dict[str, dict[str, Any]]) -> dict[str, dict[str, float]]:
    def mean(metric: str, names: list[str]) -> float:
        return float(np.mean([per_sequence[name][metric] for name in names]))

    names = sorted(labels)
    groups = {
        scenario: sorted(n for n in names if labels[n]["scenario"] == scenario)
        for scenario in ("structured", "tunnel")
    }
    core = {
        "avg_translation_error_pct": mean("translation_error_pct", names),
        "avg_rotation_error_deg_per_100m": mean("rotation_error_deg_per_100m", names),
        "endpoint_position_error_m": mean("endpoint_position_error_m", names),
        "path_length_error_pct": mean("path_length_error_pct", names),
    }
    out = {"core": core, "ablation": dict(core, velocity_rmse_mps=mean("velocity_rmse_mps", names))}
    for scenario, members in groups.items():
        out[scenario] = {
            key: mean(key, members)
            for key in (
                "translation_error_pct",
                "rotation_error_deg_per_100m",
                "endpoint_position_error_m",
                "path_length_error_pct",
            )
        }
    return out


def failed_aggregate() -> dict[str, dict[str, float]]:
    core = {
        "avg_translation_error_pct": CEILING["translation_error_pct"],
        "avg_rotation_error_deg_per_100m": CEILING["rotation_error_deg_per_100m"],
        "endpoint_position_error_m": CEILING["endpoint_position_error_m"],
        "path_length_error_pct": CEILING["path_length_error_pct"],
    }
    scenario = {
        "translation_error_pct": CEILING["translation_error_pct"],
        "rotation_error_deg_per_100m": CEILING["rotation_error_deg_per_100m"],
        "endpoint_position_error_m": CEILING["endpoint_position_error_m"],
        "path_length_error_pct": CEILING["path_length_error_pct"],
    }
    return {
        "core": core,
        "ablation": dict(core, velocity_rmse_mps=CEILING["velocity_rmse_mps"]),
        "structured": dict(scenario),
        "tunnel": dict(scenario),
    }


def artifact_name(path: Path, artifact: Any) -> str:
    name = artifact.get("method") if isinstance(artifact, dict) else None
    if isinstance(name, str) and NAME_RE.match(name):
        return name
    stem = path.name.removesuffix(".json").removesuffix("_predictions")
    cleaned = re.sub(r"[^A-Za-z0-9_.\-]", "_", stem)[:64]
    return cleaned or "unnamed"


def build_scores(prediction_paths: list[Path], inputs_path: Path) -> dict[str, Any]:
    expected_digest, labels = load_labels()
    if inputs_path.is_file():
        inputs_ok = inputs_digest(inputs_path) == expected_digest
        inputs_status = "verified" if inputs_ok else "modified"
    else:
        inputs_ok = False
        inputs_status = "missing"

    rows: dict[str, dict[str, dict[str, float]]] = {}
    comparator_names = []
    for path in sorted(COMPARATOR_DIR.glob("*.json")):
        artifact = json.loads(path.read_text())
        name = artifact["method"]
        rows[name] = aggregate(score_sequences(artifact["sequences"], labels), labels)
        comparator_names.append(name)
    if BASELINE_ROW not in rows:
        raise RuntimeError(f"missing frozen comparator {BASELINE_ROW!r} in {COMPARATOR_DIR}")
    baseline_te = rows[BASELINE_ROW]["core"]["avg_translation_error_pct"]

    ignored = []
    failed: dict[str, str] = {}
    claimed: dict[str, list[tuple[Path, Any]]] = {}
    for path in prediction_paths:
        try:
            artifact = json.loads(path.read_text())
        except (OSError, ValueError):
            artifact = None
        name = artifact_name(path, artifact)
        if name in RESERVED_NAMES or name.lower() in RESERVED_NAMES:
            ignored.append({"file": str(path), "reason": f"{name!r} is a fixed comparator row owned by the evaluator"})
            continue
        claimed.setdefault(name, []).append((path, artifact))

    method_names = sorted(claimed)
    for name in method_names:
        entries = claimed[name]
        reason = None
        aggregates = None
        if len(entries) > 1:
            reason = "several artifacts claim this method name: " + ", ".join(str(p) for p, _ in entries)
        elif not isinstance(entries[0][1], dict):
            reason = "artifact is not a JSON object"
        elif not inputs_ok:
            reason = f"test inputs {inputs_path} are {inputs_status}"
        else:
            try:
                aggregates = aggregate(score_sequences(entries[0][1].get("sequences"), labels), labels)
            except InvalidPrediction as exc:
                reason = str(exc)
        if aggregates is not None and aggregates["core"]["avg_translation_error_pct"] >= baseline_te:
            reason = "average translation error is not better than fixed-velocity dead reckoning"
        if reason is not None:
            failed[name] = reason
            aggregates = failed_aggregate()
        rows[name] = aggregates

    order = comparator_names + method_names
    experiments = {
        "synthetic_doppler_core": {"results": {n: rows[n]["core"] for n in order}},
        "synthetic_doppler_structured": {"results": {n: rows[n]["structured"] for n in order}},
        "synthetic_doppler_tunnel": {"results": {n: rows[n]["tunnel"] for n in order}},
        "synthetic_doppler_ablation": {
            "results": {n: rows[n]["ablation"] for n in order if n != BASELINE_ROW}
        },
    }
    return {
        "_metadata": {
            "slice": SLICE_NAME,
            "split": "held-out sequences (labels only in eval/test/)",
            "sequences": len(labels),
            "frames_per_sequence": sorted({len(v["frame_times"]) for v in labels.values()}),
            "segment_lengths_m": list(SEGMENT_LENGTHS_M),
            "comparator_rows": comparator_names,
            "test_inputs": {"path": str(inputs_path), "status": inputs_status},
            "prediction_files": [str(p) for p in prediction_paths],
            "ignored_artifacts": ignored,
            "failed_methods": failed,
            "ceilings": CEILING,
        },
        "experiments": experiments,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", nargs="*", default=[])
    parser.add_argument("--inputs", default=str(DEFAULT_INPUTS))
    parser.add_argument("--output", default="scoring/scores_test.json")
    args = parser.parse_args()

    scores = build_scores([Path(p) for p in args.predictions], Path(args.inputs))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(scores, indent=2, allow_nan=False)
    out.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
