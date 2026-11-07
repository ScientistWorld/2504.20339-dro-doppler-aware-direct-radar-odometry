#!/bin/bash
# Choose the combined-objective weight on the train split only and write
# method/dro_config.json (already committed; rerun only to re-tune).

set -e

cd "$(dirname "$0")/.."

[ -f data/train.npz ] || bash scripts/download.sh
python method/tune_gd_weight.py --train data/train.npz --cache-dir checkpoints/cache
