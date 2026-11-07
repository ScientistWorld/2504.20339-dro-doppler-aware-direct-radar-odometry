#!/bin/bash
# Run the full method (DRO-GD) on every train and test sequence.
# Writes checkpoints/dro_synthetic/dro_gd_predictions.json.

set -e

cd "$(dirname "$0")/.."

[ -f data/train.npz ] || bash scripts/download.sh
python method/dro_synthetic.py --mode dro_gd \
  --inputs data/train.npz data/test_inputs.npz \
  --output checkpoints/dro_synthetic/dro_gd_predictions.json \
  --cache-dir checkpoints/cache
