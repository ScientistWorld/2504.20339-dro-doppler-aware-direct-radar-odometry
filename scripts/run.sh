#!/bin/bash
# CPU validation job: regenerate the synthetic benchmark artifacts, score the
# standard and split evaluators, and validate the packaged workspace.

set -e

cd "$(dirname "$0")/.."

bash scripts/reproduce.sh
bash scripts/evaluate_train.sh
bash scripts/evaluate_test.sh
python validate.py
python validate.py --compare
