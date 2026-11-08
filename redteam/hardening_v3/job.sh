#!/bin/bash
# Final hardening job (CPU). Rebuilds the gym from the final code and replays
# the audit through the hidden test:
#   1. regenerate the train split and the 12-sequence held-out split with the
#      random-process motion model (deterministic; reruns hit the caches);
#   2. re-select the combined-objective weight on train;
#   3. comparators (dead reckoning, DRO-D, DRO-G) and the reference DRO-GD;
#   4. freeze comparator rows into eval/, write all score files, validate;
#   5. audit: cheap variants and shortcuts first, then the two method reruns.
# Resumable: per-sequence method outputs are cached under checkpoints/.

set -e

cd "$(dirname "$0")/../.."
export PYTHONDONTWRITEBYTECODE=1

echo "== $(date) resources"
nproc || true
cat /sys/fs/cgroup/cpu.max 2>/dev/null || true
python -c "import sys; sys.path.insert(0, 'method'); import dro_synthetic as d; print('dro workers', d.available_workers())"

echo "== $(date) data: train split and held-out split"
python data/synthetic_radar.py --output data/train.npz
python eval/test/make_test_set.py --force

echo "== $(date) tune combined-objective weight on train"
bash scripts/tune.sh
cat method/dro_config.json

echo "== $(date) comparators"
bash scripts/baseline.sh
bash scripts/ablations.sh

echo "== $(date) reference method"
bash scripts/method.sh
python scripts/freeze_comparators.py

echo "== $(date) scoring"
bash scripts/evaluate.sh > /dev/null
bash scripts/evaluate_train.sh > /dev/null
bash scripts/evaluate_test.sh > /dev/null
python - <<'PY'
import json
for split in ("train", "test"):
    s = json.load(open(f"scoring/scores_{split}.json"))
    print(split, "failed:", json.dumps(s["_metadata"]["failed_methods"]), "eligibility:", json.dumps(s["_metadata"]["eligibility"]))
    for exp, d in s["experiments"].items():
        for name, row in d["results"].items():
            print(f"  {split:5s} {exp:30s} {name:22s}", {k: round(v, 4) for k, v in row.items()})
d = json.load(open("checkpoints/dro_synthetic/dro_gd_predictions.json"))
for n, e in d["sequences"].items():
    print("gyro bias", n, round(e["gyro_bias_estimate"], 5), e["stationary_frames"])
PY
python validate.py || echo "validate.py reported errors (continuing)"

echo "== $(date) audit: cheap cases"
python redteam/hardening_v3/audit.py --skip-expensive || echo "audit (cheap) failed"
echo "== $(date) audit: method reruns"
python redteam/hardening_v3/audit.py || echo "audit failed"
echo "== $(date) done"
