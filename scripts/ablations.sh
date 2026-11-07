#!/bin/bash
# Reference variants used as fixed comparator rows: Doppler-only (dro_d) and
# direct-registration-only (dro_g). Outputs use the *_comparator.json suffix
# so the evaluators do not treat them as submitted methods.

set -e

cd "$(dirname "$0")/.."

[ -f data/train.npz ] || bash scripts/download.sh
for mode in dro_d dro_g; do
  python method/dro_synthetic.py --mode "$mode" \
    --inputs data/train.npz data/test_inputs.npz \
    --output "checkpoints/comparators/${mode}_comparator.json" \
    --cache-dir checkpoints/cache
done
