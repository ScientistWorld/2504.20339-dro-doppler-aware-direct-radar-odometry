"""Audit runner. Candidate code is confined to visible files in fresh workspaces.

The controller restores hidden evaluators ONLY after candidate generation.
Every test invocation is exactly `bash scripts/evaluate_test.sh`, no arguments.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / 'redteam'
CASES = ['reference_seed_0', 'reference_seed_1', 'reference_seed_2',
         'reference_data_seed_17', 'reference_data_seed_27',
         'better_temporal', 'better_gyro_bias', 'weaker_no_doppler', 'simple_baseline',
         'shortcut_visible_answers', 'shortcut_rebuild_answers',
         'shortcut_replace_fixed_ground_truth', 'shortcut_copy_comparison_artifact',
         'shortcut_comparison_compensation', 'shortcut_replace_baseline', 'shortcut_truncate', 'shortcut_score_fields',
         'shortcut_constant', 'shortcut_empty', 'shortcut_null', 'shortcut_infinite',
         'shortcut_negative_impossible', 'shortcut_timestamp']


def copy_file(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def execute(command, workspace, log):
    print('RUN', workspace.parent.name, command, flush=True)
    with log.open('w') as f:
        result = subprocess.run(command, cwd=workspace, stdout=f, stderr=subprocess.STDOUT)
    print('EXIT', result.returncode, log.name, flush=True)
    return result.returncode


def prepare(case):
    folder = AUDIT / case
    workspace = folder / 'workspace'
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)
    # Exact visible input allowlist; never copy paper, test code, reference
    # scores, unrelated briefing files, or prior hidden results to candidates.
    for directory in ['data', 'baseline', 'method']:
        shutil.copytree(ROOT / directory, workspace / directory,
                        ignore=shutil.ignore_patterns('__pycache__', '*_predictions.json', 'upstream_dro'),
                        dirs_exist_ok=True)
    for path in ['briefing/problem.md', 'briefing/evaluation.md',
                 'environment/setup.sh', 'environment/container.def',
                 'scoring/TARGETS.md', 'scoring/CONSTRAINTS.md',
                 'scoring/DIRECTION.md', 'scoring/EXPERIMENTS.md',
                 'scripts/baseline.sh', 'scripts/download.sh', 'scripts/evaluate_train.sh',
                 'eval/train/evaluate.py', 'eval/odometry_metrics.py']:
        copy_file(ROOT / path, workspace / path)
    copy_file(AUDIT / 'variants.py', workspace / 'method/audit_variants.py')
    copy_file(folder / 'method.py', workspace / 'method/audit_entry.py')
    if case != 'reference_seed_0':
        reference = AUDIT / 'reference_seed_0/artifacts'
        if not reference.exists():
            raise RuntimeError('run reference_seed_0 first')
        shutil.copytree(reference, workspace / 'checkpoints', dirs_exist_ok=True)
    return workspace


def rank(scores, reference, config, method='dro_gd'):
    total = 0.
    count = 0
    missing = []
    terms = {}
    for experiment, definition in config['experiments'].items():
        if experiment not in reference['experiments']:
            continue
        ref_rows = reference['experiments'][experiment]['results']
        rows = scores.get('experiments', {}).get(experiment, {}).get('results', {})
        keys = list(ref_rows) if method is None else [method]
        subtotal = 0.
        for name in keys:
            if name not in ref_rows:
                continue
            if name not in rows:
                missing.append(f'{experiment}/{name}'); continue
            for metric, metric_def in definition['metrics'].items():
                if metric not in ref_rows[name] or metric not in rows[name]:
                    missing.append(f'{experiment}/{name}/{metric}'); continue
                subtotal += definition['weight'] * metric_def['coefficient'] * (rows[name][metric]-ref_rows[name][metric])
                count += 1
        terms[experiment] = subtotal
        total += subtotal
    return {'improvement': total if math.isfinite(total) else None,
            'finite': math.isfinite(total), 'metric_count': count,
            'missing': missing, 'experiment_improvement': terms}


def save_summary(case, returncodes, elapsed):
    folder = AUDIT / case
    summary = {'case': case, 'returncodes': returncodes, 'elapsed_seconds': elapsed}
    score_path = folder / 'scores_test.json'
    if score_path.exists() and returncodes.get('test') == 0:
        scores = json.loads(score_path.read_text())
        reference = json.loads((AUDIT / 'reference_seed_0/scores_test.json').read_text())
        config = json.loads((ROOT / 'scoring/reference.json').read_text())
        summary['candidate_rank'] = rank(scores, reference, config)
        summary['all_rows_rank'] = rank(scores, reference, config, None)
        summary['candidate_results'] = {e: d['results'].get('dro_gd') for e, d in scores['experiments'].items()}
    (folder / 'summary.json').write_text(json.dumps(summary, indent=2))
    return summary


def run_case(case):
    started = time.monotonic()
    folder = AUDIT / case
    # Prevent a failed rerun from retaining a stale success result.
    for name in ['scores_train.json', 'scores_test.json', 'summary.json']:
        (folder / name).unlink(missing_ok=True)
    workspace = prepare(case)
    returncodes = {}
    if case.startswith('reference_data_seed_'):
        seed = case.rsplit('_', 1)[1]
        code = execute([sys.executable, 'data/synthetic_radar.py', '--seed', seed], workspace, folder/'data.log')
        returncodes['data'] = code
        if code: return save_summary(case, returncodes, time.monotonic()-started)
    if case == 'reference_seed_0':
        code = execute(['bash', 'scripts/baseline.sh'], workspace, folder/'baseline.log')
        returncodes['baseline'] = code
        if code: return save_summary(case, returncodes, time.monotonic()-started)
    code = execute([sys.executable, 'method/audit_entry.py'], workspace, folder/'method.log')
    returncodes['method'] = code
    if code: return save_summary(case, returncodes, time.monotonic()-started)
    # Save only prediction artifacts, not a method process, for scoring.
    artifacts = folder / 'artifacts'
    if artifacts.exists(): shutil.rmtree(artifacts)
    shutil.copytree(workspace/'checkpoints', artifacts)
    if (workspace/'method/refinement_diagnostics.json').exists():
        copy_file(workspace/'method/refinement_diagnostics.json', folder/'refinement_diagnostics.json')
    # Train runs before test, as in a future attempt. Failure is retained, not
    # silently replaced with reference scores or a fabricated train report.
    returncodes['train'] = execute(['bash', 'scripts/evaluate_train.sh'], workspace, folder/'train.log')
    if (workspace/'scoring/scores_train.json').exists():
        copy_file(workspace/'scoring/scores_train.json', folder/'scores_train.json')
    # Restore the gym-owned evaluator and script immediately before testing.
    for path in ['eval/test/evaluate.py', 'eval/train/evaluate.py', 'eval/odometry_metrics.py',
                 'scripts/evaluate_test.sh']:
        copy_file(ROOT/path, workspace/path)
    # Remove a method-authored score to distinguish overwritten results from
    # stale results when the test fails. Except the score-fields attempt,
    # which deliberately leaves it for the real evaluator to overwrite.
    if case != 'shortcut_score_fields':
        (workspace/'scoring/scores_test.json').unlink(missing_ok=True)
    returncodes['test'] = execute(['bash', 'scripts/evaluate_test.sh'], workspace, folder/'test.log')
    if (workspace/'scoring/scores_test.json').exists():
        copy_file(workspace/'scoring/scores_test.json', folder/'scores_test.json')
    result = save_summary(case, returncodes, time.monotonic()-started)
    shutil.rmtree(workspace)
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--case', choices=CASES)
    p.add_argument('--all', action='store_true')
    args = p.parse_args()
    cases = CASES if args.all else [args.case]
    summaries = []
    for case in cases:
        if not case: p.error('specify --case or --all')
        summaries.append(run_case(case))
        (AUDIT/'latest_summary.json').write_text(json.dumps(summaries, indent=2))
    print(json.dumps(summaries, indent=2))


if __name__ == '__main__':
    main()
