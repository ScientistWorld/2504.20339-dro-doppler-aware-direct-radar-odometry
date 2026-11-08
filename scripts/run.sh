#!/bin/bash
# CPU job for the final hardening iteration: rebuild data, comparators and
# the reference from the final code, score, validate, and replay the audit.
# (After this job, run.sh goes back to `bash scripts/reproduce.sh`.)

set -e

cd "$(dirname "$0")/.."

bash redteam/hardening_v3/job.sh
