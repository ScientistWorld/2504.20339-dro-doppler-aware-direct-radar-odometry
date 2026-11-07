#!/bin/bash
# This job: the hardening pipeline (see redteam/hardening/job.sh).
set -e
cd "$(dirname "$0")/.."
bash redteam/hardening/job.sh
