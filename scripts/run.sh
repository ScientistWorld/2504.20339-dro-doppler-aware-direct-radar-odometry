#!/bin/bash
# Audit job: regenerate data, run baseline and revised DRO variants, then score
# aggregate and per-scenario replacement benchmark experiments.

set -e

cd /home/user

bash scripts/reproduce.sh
python validate.py --compare
