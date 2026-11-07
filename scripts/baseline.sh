#!/bin/bash
# Fixed-velocity gyro dead reckoning comparator on every sequence. The
# evaluators score frozen copies of this output (eval/*/comparators/).

set -e

cd "$(dirname "$0")/.."

[ -f data/train.npz ] || bash scripts/download.sh
python baseline/dead_reckoning.py --inputs data/train.npz data/test_inputs.npz \
  --output checkpoints/comparators/fixed_velocity_gyro_comparator.json
