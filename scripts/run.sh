#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
# CPU audit: all inference and generated data stay on the job node.
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
python3 redteam/audit.py --all
