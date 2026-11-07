#!/bin/bash
# Estimated download size: 0 MB. Disk usage: ~15 MB, all tracked in git.
#
# The paper's real datasets are large (Boreas, MulRan) or not public (the
# Doppler-enabled automotive set), so this benchmark uses procedurally
# rendered spinning FMCW radar sequences. Both files are agent-authored,
# small, and tracked in the repository:
#   data/train.npz        labelled training sequences; if absent it is
#                         restored from git, or rebuilt from
#                         data/synthetic_radar.py (deterministic seeds);
#   data/test_inputs.npz  held-out sequences, inputs only (scans, gyro,
#                         frame times); restored from git if absent.
# No external fetch is required.

set -e

cd "$(dirname "$0")/.."

mkdir -p data data/downloads
if [ ! -f data/train.npz ]; then
  git checkout -- data/train.npz 2>/dev/null || python data/synthetic_radar.py --output data/train.npz
fi
if [ ! -f data/test_inputs.npz ]; then
  git checkout -- data/test_inputs.npz
fi
