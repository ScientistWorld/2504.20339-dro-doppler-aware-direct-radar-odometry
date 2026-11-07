#!/bin/bash
# Score every prediction artifact on disk against the held-out test labels.
# Runs with no arguments; labels and comparator rows live in eval/test/.

set -e

cd "$(dirname "$0")/.."

mkdir -p scoring
predictions=("$@")
if [ ${#predictions[@]} -eq 0 ]; then
  mapfile -t predictions < <(
    find checkpoints method baseline -type f -name '*_predictions.json' 2>/dev/null | sort
  )
fi

python eval/test/evaluate.py \
  --inputs data/test_inputs.npz \
  --output scoring/scores_test.json \
  --predictions "${predictions[@]}"
