#!/bin/bash
# Evaluate held-out test-slice odometry scores from prediction JSON artifacts.

set -e

cd /home/user

mkdir -p scoring

predictions=("$@")
if [ ${#predictions[@]} -eq 0 ]; then
  mapfile -t predictions < <(
    find checkpoints method baseline -type f -name '*_predictions.json' 2>/dev/null | sort
  )
fi

if [ ${#predictions[@]} -eq 0 ]; then
  echo "No prediction JSON artifacts found. Pass files explicitly or generate checkpoints first." >&2
  exit 1
fi

python eval/test/evaluate.py \
  --predictions "${predictions[@]}" \
  --data data/synthetic_dro.npz \
  --output scoring/scores_test.json \
  --match-train scoring/scores_train.json
