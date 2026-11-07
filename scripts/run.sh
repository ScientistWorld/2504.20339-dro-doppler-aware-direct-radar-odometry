#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
python redteam/audit_v2/controller.py --case shortcut_rebuild_answers_v2 --force
python redteam/audit_v2/controller.py --case shortcut_calibration_zero_velocity_v2
