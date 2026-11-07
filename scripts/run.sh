#!/bin/bash
# Hardening job (CPU): build the held-out test split, regenerate the train
# split, tune the combined-objective weight on train, run comparators and the
# reference method, freeze comparator rows into the evaluators, score, and
# replay variants/shortcuts through the hidden test. Resumable: per-sequence
# method outputs and finished audit cases are cached.

set -e

cd "$(dirname "$0")/.."

echo "== $(date) build held-out test split"
python eval/test/make_test_set.py
echo "== $(date) train split"
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
PY
python validate.py || echo "validate.py reported errors (continuing)"
echo "== $(date) hardening audit"
python redteam/hardening/audit.py --all || echo "audit reported errors"
echo "== $(date) done"
