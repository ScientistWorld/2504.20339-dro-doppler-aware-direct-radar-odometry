"""Hardening audit controller.

For every case: build a fresh workspace from the files a future agent sees,
run the candidate (redteam/hardening/cases.py) there, run the visible train
scorer, then restore the hidden eval/test/ and scripts/evaluate_test.sh from
the gym and run `bash scripts/evaluate_test.sh` with no arguments. Ranks are
computed against the reference scoring/scores_test.json with the weights and
signed coefficients of scoring/reference.json:

    rank = sum_exp sum_metric weight * coefficient * (new - reference)

`candidate_rank` uses the dro_gd row only; `all_rows_rank` sums every row of
the reference report (comparator rows included).

Usage: python redteam/hardening/audit.py --all     (resumes finished cases)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNS = HERE / "runs"
WS_ROOT = ROOT / "tmp" / "hardening_ws"

VARIANTS = [
    "reference",
    "better_gp_alignment",
    "weaker_no_gyro_bias",
    "weaker_no_doppler",
    "prior_constant_motion_fit",
    "simple_baseline",
]
SHORTCUTS = [
    "shortcut_visible_answers",
    "shortcut_rebuild_answers",
    "shortcut_replace_fixed_ground_truth",
    "shortcut_truncate",
    "shortcut_copy_comparison_artifact",
    "shortcut_comparison_compensation",
    "shortcut_replace_baseline",
    "shortcut_score_fields",
    "shortcut_timestamp",
    "shortcut_constant",
    "shortcut_empty",
    "shortcut_null",
    "shortcut_infinite",
    "shortcut_negative_impossible",
    "shortcut_duplicate_name",
]
EXPENSIVE = {"better_gp_alignment", "weaker_no_gyro_bias"}
# Cheap cases first so a partial run still yields the shortcut results.
CASES = [c for c in VARIANTS + SHORTCUTS if c not in EXPENSIVE] + [c for c in VARIANTS if c in EXPENSIVE]
KEEP_PREDICTIONS = {"reference", "better_gp_alignment", "weaker_no_gyro_bias", "prior_constant_motion_fit"}

VISIBLE_DIRS = ["data", "method", "baseline", "eval/train"]
VISIBLE_FILES = [
    "scripts/download.sh", "scripts/method.sh", "scripts/baseline.sh", "scripts/ablations.sh",
    "scripts/evaluate.sh", "scripts/evaluate_train.sh", "briefing/problem.md", "briefing/evaluation.md",
    "scoring/TARGETS.md", "scoring/CONSTRAINTS.md", "scoring/DIRECTION.md", "scoring/EXPERIMENTS.md",
]


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def prepare(case: str) -> Path:
    ws = WS_ROOT / case
    parked = WS_ROOT / f"{case}.cache"
    if (ws / "checkpoints" / "cache").exists():
        if parked.exists():
            shutil.rmtree(parked)
        shutil.move(str(ws / "checkpoints" / "cache"), str(parked))
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    ignore = shutil.ignore_patterns("__pycache__", "upstream_dro", "downloads", "*.pyc")
    for d in VISIBLE_DIRS:
        shutil.copytree(ROOT / d, ws / d, ignore=ignore, dirs_exist_ok=True)
    for f in VISIBLE_FILES:
        copy_file(ROOT / f, ws / f)
    for d in ["checkpoints/dro_synthetic", "checkpoints/comparators"]:
        shutil.copytree(ROOT / d, ws / d, dirs_exist_ok=True)
    copy_file(HERE / "cases.py", ws / "method" / "hardening_case.py")
    if parked.exists():
        shutil.move(str(parked), str(ws / "checkpoints" / "cache"))
    return ws


def execute(cmd: list[str], ws: Path, log: Path) -> int:
    print("RUN", ws.name, " ".join(cmd), flush=True)
    with log.open("w") as f:
        rc = subprocess.run(cmd, cwd=ws, stdout=f, stderr=subprocess.STDOUT).returncode
    print("EXIT", rc, log.name, flush=True)
    return rc


def rank(scores: dict, reference: dict, config: dict, rows: list[str] | None) -> dict:
    total = 0.0
    terms = {}
    missing = []
    count = 0
    for exp, definition in config["experiments"].items():
        ref_rows = reference["experiments"].get(exp, {}).get("results", {})
        if not ref_rows:
            continue
        new_rows = scores.get("experiments", {}).get(exp, {}).get("results", {})
        sub = 0.0
        for name in (rows if rows is not None else list(ref_rows)):
            if name not in ref_rows:
                continue
            if name not in new_rows:
                missing.append(f"{exp}/{name}")
                continue
            for metric, mdef in definition["metrics"].items():
                if metric in ref_rows[name] and metric in new_rows[name]:
                    sub += definition["weight"] * mdef["coefficient"] * (new_rows[name][metric] - ref_rows[name][metric])
                    count += 1
        terms[exp] = sub
        total += sub
    return {"rank": total if math.isfinite(total) else None, "metric_count": count, "missing": missing, "per_experiment": terms}


def run_case(case: str, force: bool) -> dict:
    out = RUNS / case
    summary_path = out / "summary.json"
    if summary_path.exists() and not force:
        return json.loads(summary_path.read_text())
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("*"):
        if stale.is_file():
            stale.unlink()
    start = time.monotonic()
    ws = prepare(case)
    rc = {"method": execute([sys.executable, "method/hardening_case.py", case], ws, out / "method.log")}
    summary: dict = {"case": case, "returncodes": rc}
    if rc["method"] == 0:
        rc["train"] = execute(["bash", "scripts/evaluate_train.sh"], ws, out / "train.log")
        if (ws / "scoring/scores_train.json").exists():
            copy_file(ws / "scoring/scores_train.json", out / "scores_train.json")
        # Restore the gym-owned hidden evaluator before the test run.
        shutil.rmtree(ws / "eval" / "test", ignore_errors=True)
        shutil.copytree(ROOT / "eval" / "test", ws / "eval" / "test", ignore=shutil.ignore_patterns("__pycache__"))
        copy_file(ROOT / "scripts/evaluate_test.sh", ws / "scripts/evaluate_test.sh")
        if case != "shortcut_score_fields":
            (ws / "scoring/scores_test.json").unlink(missing_ok=True)
        rc["test"] = execute(["bash", "scripts/evaluate_test.sh"], ws, out / "test.log")
        if rc["test"] == 0 and (ws / "scoring/scores_test.json").exists():
            copy_file(ws / "scoring/scores_test.json", out / "scores_test.json")
            scores = json.loads((out / "scores_test.json").read_text())
            reference = json.loads((ROOT / "scoring/scores_test.json").read_text())
            config = json.loads((ROOT / "scoring/reference.json").read_text())
            summary["candidate_rank"] = rank(scores, reference, config, ["dro_gd"])
            summary["all_rows_rank"] = rank(scores, reference, config, None)
            summary["candidate_results"] = {
                e: d["results"].get("dro_gd") for e, d in scores["experiments"].items()
            }
            summary["failed_methods"] = scores["_metadata"]["failed_methods"]
            summary["ignored_artifacts"] = scores["_metadata"]["ignored_artifacts"]
            summary["test_inputs"] = scores["_metadata"]["test_inputs"]
            summary["identical_to_reference_report"] = scores["experiments"] == reference["experiments"]
        if case in KEEP_PREDICTIONS and (ws / "checkpoints/dro_synthetic/dro_gd_predictions.json").exists():
            copy_file(ws / "checkpoints/dro_synthetic/dro_gd_predictions.json", out / "dro_gd_predictions.json")
        if (ws / "method/rebuild_matches.json").exists():
            copy_file(ws / "method/rebuild_matches.json", out / "rebuild_matches.json")
    summary["elapsed_seconds"] = time.monotonic() - start
    summary_path.write_text(json.dumps(summary, indent=2))
    shutil.rmtree(ws, ignore_errors=True)
    return summary


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def analyze() -> dict:
    """Per-sequence statistics, gyro-bias diagnostics and rank sanity checks."""
    test_eval = load_module(ROOT / "eval/test/evaluate.py", "hidden_eval")
    _, labels = test_eval.load_labels()
    seq_names = sorted(labels)
    config = json.loads((ROOT / "scoring/reference.json").read_text())
    reference = json.loads((ROOT / "scoring/scores_test.json").read_text())
    train_scores = json.loads((ROOT / "scoring/scores_train.json").read_text())

    sources = {"dro_gd (reference)": ROOT / "checkpoints/dro_synthetic/dro_gd_predictions.json"}
    for path in sorted((ROOT / "eval/test/comparators").glob("*.json")):
        sources[f"{path.stem} (comparator)"] = path
    for case in ["better_gp_alignment", "weaker_no_gyro_bias", "prior_constant_motion_fit"]:
        p = RUNS / case / "dro_gd_predictions.json"
        if p.exists():
            sources[case] = p
    per_seq = {}
    for label, path in sources.items():
        art = json.loads(path.read_text())
        per_seq[label] = test_eval.score_sequences(art["sequences"], labels)

    def stats(values):
        arr = np.asarray(values, dtype=float)
        return {"mean": float(arr.mean()), "std": float(arr.std(ddof=1)), "se": float(arr.std(ddof=1) / np.sqrt(len(arr))),
                "min": float(arr.min()), "max": float(arr.max())}

    ref_label = "dro_gd (reference)"
    out: dict = {"per_sequence": per_seq, "scenario_of": {n: labels[n]["scenario"] for n in seq_names}}
    out["reference_translation_stats"] = stats([per_seq[ref_label][n]["translation_error_pct"] for n in seq_names])
    paired = {}
    for label in per_seq:
        if label == ref_label:
            continue
        diffs = {}
        for metric in ("translation_error_pct", "rotation_error_deg_per_100m", "velocity_rmse_mps"):
            d = [per_seq[label][n][metric] - per_seq[ref_label][n][metric] for n in seq_names]
            diffs[metric] = {**stats(d), "sequences_improved": int(sum(x < 0 for x in d))}
        paired[label] = diffs
    out["paired_vs_reference"] = paired

    # Train vs test reference (independent draws of the same generator).
    out["reference_train_vs_test"] = {
        exp: {"train": train_scores["experiments"][exp]["results"].get("dro_gd"),
              "test": reference["experiments"][exp]["results"].get("dro_gd")}
        for exp in reference["experiments"]
    }

    # Gyro-bias diagnostics against the generator's true bias.
    gen = load_module(ROOT / "data/synthetic_radar.py", "gen")
    hidden = load_module(ROOT / "eval/test/make_test_set.py", "make_test_set")
    true_bias = {name: gen.simulate_motion(sc, seed)["profile"]["gyro_bias"] for name, sc, seed in gen.TRAIN_SEQUENCES}
    true_bias.update({name: gen.simulate_motion(sc, seed)["profile"]["gyro_bias"] for name, sc, seed in hidden.TEST_SEQUENCES})
    ref_art = json.loads((ROOT / "checkpoints/dro_synthetic/dro_gd_predictions.json").read_text())
    out["gyro_bias"] = {
        name: {"true": true_bias[name], "estimate": entry.get("gyro_bias_estimate"), "stationary_frames": entry.get("stationary_frames")}
        for name, entry in ref_art["sequences"].items()
    }

    # A method that fails the task (translation error just below the
    # dead-reckoning gate) but is perfect on every other metric.
    base = reference["experiments"]
    core_base = base["synthetic_doppler_core"]["results"]["fixed_velocity_gyro"]
    hypo = {"experiments": {}}
    for exp, data in base.items():
        b = data["results"].get("fixed_velocity_gyro", core_base)
        row = {}
        for metric in data["results"]["dro_gd"]:
            if "translation" in metric:
                row[metric] = 0.999 * b.get(metric, core_base["avg_translation_error_pct"])
            else:
                row[metric] = 0.0
        hypo["experiments"][exp] = {"results": {"dro_gd": row}}
    out["task_failure_perfect_elsewhere_rank"] = rank(hypo, reference, config, ["dro_gd"])["rank"]
    perfect = {"experiments": {e: {"results": {"dro_gd": {m: 0.0 for m in d["results"]["dro_gd"]}}}} for e, d in base.items()}
    out["perfect_method_rank"] = rank(perfect, reference, config, ["dro_gd"])["rank"]
    out["reference_values"] = {e: d["results"]["dro_gd"] for e, d in base.items()}
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=CASES, action="append")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    cases = CASES if args.all else (args.case or [])
    summaries = {}
    for case in cases:
        try:
            summaries[case] = run_case(case, args.force)
        except Exception as exc:  # keep auditing the remaining cases
            summaries[case] = {"case": case, "error": repr(exc)}
        (HERE / "results.json").write_text(json.dumps({"cases": summaries}, indent=2))
    results = {"cases": summaries}
    try:
        results["analysis"] = analyze()
    except Exception as exc:
        results["analysis_error"] = repr(exc)
    (HERE / "results.json").write_text(json.dumps(results, indent=2))
    for case, s in summaries.items():
        cr = (s.get("candidate_rank") or {}).get("rank")
        ar = (s.get("all_rows_rank") or {}).get("rank")
        print(f"{case:40s} candidate={cr} all_rows={ar} failed={list((s.get('failed_methods') or {}).items())[:2]}")


if __name__ == "__main__":
    main()
