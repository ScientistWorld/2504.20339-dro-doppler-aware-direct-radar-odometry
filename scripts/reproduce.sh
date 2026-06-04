#!/bin/bash
# End-to-end reproduction script for the packaged DRO benchmark.

set -e

cd /home/user

bash scripts/download.sh
bash scripts/baseline.sh
bash scripts/method.sh
bash scripts/evaluate.sh
