#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 redteam/audit.py --case shortcut_rebuild_answers
