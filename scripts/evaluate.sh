#!/bin/bash
# Evaluate prediction JSON artifacts with method-agnostic odometry metrics.

set -e

cd "$(dirname "$0")/.."

mkdir -p scoring

predictions=("$@")
if [ ${#predictions[@]} -eq 0 ]; then
  predictions=(
    checkpoints/baseline/dead_reckoning_predictions.json
    checkpoints/dro_synthetic/dro_d_predictions.json
    checkpoints/dro_synthetic/dro_g_predictions.json
    checkpoints/dro_synthetic/dro_gd_predictions.json
  )
fi

python eval/odometry_metrics.py --predictions "${predictions[@]}" --output scoring/scores.json
