#!/bin/bash
# CPU job: reproduce the reference end to end (data restore, comparators,
# method, train/test scoring) and validate the workspace. The combined-
# objective weight is read from method/dro_config.json (bash scripts/tune.sh
# re-selects it on the train split). Gym maintenance (rebuilding the hidden
# test split, freezing comparator rows, the final hardening audit) lives in
# redteam/hardening_v3/job.sh.

set -e

cd "$(dirname "$0")/.."

bash scripts/reproduce.sh
python validate.py
