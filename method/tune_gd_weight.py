"""Select the relative weight of the direct term in the combined objective.

The paper maximizes O_psi + O_d; their relative scale depends on how each
cross-correlation is normalized, so the weight of the direct term is treated
as a hyperparameter and chosen on the labelled TRAIN sequences only (the
paper tunes its parameters on extra held-out sequences of each type).
Writes method/dro_config.json; train runs are cached and reused by the main
pipeline.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dro_synthetic as dro  # noqa: E402

CANDIDATE_WEIGHTS = (0.12, 8.0, 32.0, 128.0, 512.0)
SEGMENTS_M = (20.0, 35.0, 50.0)


def relative_translation_error(traj: np.ndarray, poses: np.ndarray) -> float:
    """KITTI-style relative translation error (%) on fixed-length segments."""
    gt = poses[:, 1:4]
    travelled = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(gt[:, :2], axis=0), axis=1))])
    errors = []
    for i in range(0, len(gt) - 1, 2):
        for length in SEGMENTS_M:
            j = int(np.searchsorted(travelled, travelled[i] + length))
            if j >= len(gt):
                continue
            g = dro.rot2(gt[i, 2]).T @ (gt[j, :2] - gt[i, :2])
            p = dro.rot2(traj[i, 3]).T @ (traj[j, 1:3] - traj[i, 1:3])
            errors.append(100.0 * np.linalg.norm(p - g) / length)
    return float(np.mean(errors))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", default="data/train.npz")
    parser.add_argument("--cache-dir", default="checkpoints/cache")
    parser.add_argument("--output", default=str(dro.CONFIG_PATH))
    args = parser.parse_args()

    with np.load(args.train, allow_pickle=False) as data:
        manifest = json.loads(str(data["manifest_json"].item()))
        poses = {name: np.asarray(data[f"{name}_poses"]) for name in manifest["sequences"]}

    base = dro.load_config(None)
    table = {}
    for weight in CANDIDATE_WEIGHTS:
        cfg = dict(base, gd_direct_weight=weight)
        results = dro.run_all([args.train], "dro_gd", cfg, Path(args.cache_dir))
        errs = {name: relative_translation_error(np.asarray(res["trajectory"]), poses[name]) for name, res in results.items()}
        table[str(weight)] = {"mean": float(np.mean(list(errs.values()))), "per_sequence": errs}
        print(f"gd_direct_weight={weight}: mean train translation error {table[str(weight)]['mean']:.4f}%", flush=True)

    best = min(CANDIDATE_WEIGHTS, key=lambda w: table[str(w)]["mean"])
    Path(args.output).write_text(
        json.dumps(
            {
                "gd_direct_weight": best,
                "selected_on": "train split, mean relative translation error",
                "train_translation_error_pct": table,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"selected gd_direct_weight={best}")


if __name__ == "__main__":
    main()
