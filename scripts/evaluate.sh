#!/bin/bash
# Score prediction artifacts on the visible labelled split and write
# scoring/scores.json (same scorer as scripts/evaluate_train.sh).

set -e

cd "$(dirname "$0")/.."

mkdir -p scoring
predictions=("$@")
if [ ${#predictions[@]} -eq 0 ]; then
  mapfile -t predictions < <(
    find checkpoints method baseline -type f -name '*_predictions.json' 2>/dev/null | sort
  )
fi

python eval/train/evaluate.py \
  --data data/train.npz \
  --output scoring/scores.json \
  --predictions "${predictions[@]}"
