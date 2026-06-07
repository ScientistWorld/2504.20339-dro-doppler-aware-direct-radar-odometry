#!/bin/bash
# Run a simple gyro-aided fixed-velocity baseline for evaluator sanity checks.

set -e

cd "$(dirname "$0")/.."

[ -e data/synthetic_dro.npz ] || bash scripts/download.sh
python baseline/dead_reckoning.py --data data/synthetic_dro.npz --output-dir checkpoints/baseline
