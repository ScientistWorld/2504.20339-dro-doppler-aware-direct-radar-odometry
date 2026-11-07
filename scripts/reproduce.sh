#!/bin/bash
# End-to-end reproduction: data, comparators, method, scores.

set -e

cd "$(dirname "$0")/.."

bash scripts/download.sh
bash scripts/baseline.sh
bash scripts/ablations.sh
bash scripts/method.sh
bash scripts/evaluate.sh
bash scripts/evaluate_train.sh
bash scripts/evaluate_test.sh
