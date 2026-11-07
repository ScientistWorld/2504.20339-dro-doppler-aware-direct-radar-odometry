#!/bin/bash
# Hardening job (CPU, ~2.5 h on one core): rebuild/verify the held-out test
# split, tune the combined-objective weight on train, run comparators and the
# reference method, freeze comparator rows into eval/, score, and replay the
# variants and shortcuts through the hidden test. Resumable: per-sequence
# method outputs (checkpoints/cache) and finished audit cases are reused.

set -e

cd "$(dirname "$0")/../.."

echo "== $(date) held-out test split (no-op if present)"
python eval/test/make_test_set.py
echo "== $(date) train split (no-op if present)"
bash scripts/download.sh
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
    print(split, json.dumps(s["_metadata"]["failed_methods"]))
    for exp, d in s["experiments"].items():
        for name, row in d["results"].items():
            print(f"  {split:5s} {exp:30s} {name:22s}", {k: round(v, 4) for k, v in row.items()})
d = json.load(open("checkpoints/dro_synthetic/dro_gd_predictions.json"))
for n, e in d["sequences"].items():
    print("gyro bias", n, round(e["gyro_bias_estimate"], 5), e["stationary_frames"])
PY
python validate.py || echo "validate.py reported errors (continuing)"
echo "== $(date) hardening audit"
python redteam/hardening/audit.py --all || echo "audit reported errors"
echo "== $(date) done"
