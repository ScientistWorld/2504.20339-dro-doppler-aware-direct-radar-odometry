#!/bin/bash
# End-to-end reproduction script for the packaged DRO benchmark.

set -e

cd "$(dirname "$0")/.."

bash scripts/download.sh
bash scripts/baseline.sh
bash scripts/method.sh
bash scripts/evaluate.sh
