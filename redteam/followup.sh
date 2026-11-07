#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
for case in better_gp_alignment better_gp_alignment_temporal better_temporal_data_seed_17 better_temporal_data_seed_27 shortcut_replace_fixed_ground_truth; do
  bash "redteam/$case/run.sh"
done
