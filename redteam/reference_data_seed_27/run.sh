#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 redteam/audit.py --case reference_data_seed_27
