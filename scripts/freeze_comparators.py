"""Maintainer tool: freeze comparator predictions into the evaluators.

Copies the reference comparator outputs (fixed-velocity dead reckoning,
dro_d, dro_g) from checkpoints/comparators/ into eval/train/comparators/
(train sequences) and eval/test/comparators/ (test sequences). The scorers
read these frozen rows, so a submitted method cannot change the comparison
side. Not part of the normal pipeline; run only when the gym is rebuilt.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("fixed_velocity_gyro", "dro_d", "dro_g")
SPLITS = {"train": ROOT / "data" / "train.npz", "test": ROOT / "data" / "test_inputs.npz"}


def sequence_names(path: Path) -> list[str]:
    with np.load(path, allow_pickle=False) as data:
        return sorted(json.loads(str(data["manifest_json"].item()))["sequences"])


def main() -> None:
    for name in NAMES:
        artifact = json.loads((ROOT / "checkpoints" / "comparators" / f"{name}_comparator.json").read_text())
        for split, inputs in SPLITS.items():
            out_dir = ROOT / "eval" / split / "comparators"
            out_dir.mkdir(parents=True, exist_ok=True)
            frozen = {
                "method": name,
                "note": "Frozen comparator predictions; scored as a fixed row by the evaluator.",
                "sequences": {s: {"trajectory": artifact["sequences"][s]["trajectory"]} for s in sequence_names(inputs)},
            }
            (out_dir / f"{name}.json").write_text(json.dumps(frozen) + "\n")
            print(f"froze {name} -> {out_dir / (name + '.json')}")


if __name__ == "__main__":
    main()
