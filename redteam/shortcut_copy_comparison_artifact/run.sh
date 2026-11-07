#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 redteam/audit.py --case shortcut_copy_comparison_artifact
