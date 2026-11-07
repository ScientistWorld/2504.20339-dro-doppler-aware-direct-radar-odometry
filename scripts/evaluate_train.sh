#!/bin/bash
# Score every prediction artifact on disk against the visible train labels.

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
  --output scoring/scores_train.json \
  --predictions "${predictions[@]}"
