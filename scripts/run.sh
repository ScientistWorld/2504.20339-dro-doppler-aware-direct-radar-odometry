#!/bin/bash
# Split evaluation job: score the existing final prediction artifacts on the
# visible train slice and held-out test slice.

set -e

cd /home/user

bash scripts/evaluate_train.sh
bash scripts/evaluate_test.sh
