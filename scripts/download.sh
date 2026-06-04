#!/bin/bash
# Estimated download size: 0 MB. Estimated disk usage: ~2-5 MB generated.
#
# The paper's full public benchmarks are large robotics datasets and the
# Doppler-enabled automotive benchmark is not fully public. This reproduction
# uses a procedural local FMCW spinning-radar benchmark, so no external fetch
# is required.

set -e

cd "$(dirname "$0")/.."

mkdir -p data data/downloads
python data/synthetic_radar.py --output data/synthetic_dro.npz
