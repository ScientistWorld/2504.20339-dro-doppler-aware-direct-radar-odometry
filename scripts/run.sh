#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
# All computation belongs on the scheduled CPU node. Cases save incrementally.
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
python redteam/audit_v2/controller.py --all
