#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../.."
python redteam/audit_v2/controller.py --case shortcut_visible_answers_v2 "$@"
