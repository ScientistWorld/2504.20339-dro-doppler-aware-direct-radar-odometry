"""Build the held-out test split (maintainer tool, hidden with eval/test/).

Renders the test sequences with the public sensor/scene generator but with
seeds that exist only in this file. Writes:

* data/test_inputs.npz       radar scans, gyro, frame times (no labels);
                             tracked in git so methods can run on it.
* eval/test/test_labels.json poses and body velocities per frame, plus a
                             digest of the input file.

The evaluator never calls this script; it only reads the two outputs.
Run once with numpy available: python eval/test/make_test_set.py [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
INPUTS_PATH = ROOT / "data" / "test_inputs.npz"
LABELS_PATH = HERE / "test_labels.json"

# Hidden: (sequence name, scene type, seed). Names do not reveal the scene.
TEST_SEQUENCES = (
    ("test_00", "tunnel", 2948203948079727480),
    ("test_01", "structured", 1695886956203458073),
    ("test_02", "structured", 2734029228027341091),
    ("test_03", "tunnel", 19270606597703442),
    ("test_04", "structured", 682870475370742460),
    ("test_05", "tunnel", 1065506626223277763),
)


def load_generator():
    spec = importlib.util.spec_from_file_location("synthetic_radar", ROOT / "data" / "synthetic_radar.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if INPUTS_PATH.exists() and LABELS_PATH.exists() and not args.force:
        print(f"test split already built: {INPUTS_PATH} and {LABELS_PATH}")
        return
    gen = load_generator()
    rendered = {name: gen.render_sequence(scenario, seed) for name, scenario, seed in TEST_SEQUENCES}
    gen.write_dataset(INPUTS_PATH, rendered, include_labels=False)
    labels = {
        "inputs_file": "data/test_inputs.npz",
        "inputs_sha256": inputs_digest(INPUTS_PATH),
        "frame_period": gen.FRAME_PERIOD,
        "sequences": {
            name: {
                "scenario": seq["scenario"],
                "frame_times": seq["frame_times"].tolist(),
                "poses": seq["poses"][:, 1:4].tolist(),
                "velocities": seq["velocities"].tolist(),
            }
            for name, seq in rendered.items()
        },
    }
    LABELS_PATH.write_text(json.dumps(labels, indent=1))
    print(f"wrote {INPUTS_PATH} and {LABELS_PATH}")


if __name__ == "__main__":
    main()
