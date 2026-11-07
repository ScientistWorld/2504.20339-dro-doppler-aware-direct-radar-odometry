#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 redteam/audit.py --case better_temporal_data_seed_17
