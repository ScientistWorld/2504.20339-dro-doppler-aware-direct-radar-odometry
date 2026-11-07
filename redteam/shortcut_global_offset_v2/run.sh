#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../.."
python redteam/audit_v2/controller.py --case shortcut_global_offset_v2 "$@"
