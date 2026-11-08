"""Check saved audit evidence with the standard library; no model execution."""
from __future__ import annotations

import json
import math
from pathlib import Path

from controller import CASES, rank

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def read(path):
    return json.loads(path.read_text())


def close(a, b):
    assert math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12), (a, b)


def check_rank(actual, saved):
    # Python versions differ in floating-point summation of the same terms.
    close(actual['rank'], saved['rank'])
    assert actual['metric_count'] == saved['metric_count']
    assert actual['missing'] == saved['missing']
    assert actual['per_experiment'].keys() == saved['per_experiment'].keys()
    for name in actual['per_experiment']:
        close(actual['per_experiment'][name], saved['per_experiment'][name])


def main():
    aggregate = read(HERE / 'results.json')
    reference = read(HERE / 'reference_scores.json')
    assert len(CASES) == 26 and set(aggregate['cases']) == set(CASES)
    summaries = {}
    for case in CASES:
        folder = ROOT / 'redteam' / case
        for name in ('method.py', 'run.sh', 'candidate_predictions.json',
                     'scores_test.json', 'summary.json'):
            assert (folder / name).is_file(), (case, name)
        summary = read(folder / 'summary.json')
        scores = read(folder / 'scores_test.json')
        assert summary == aggregate['cases'][case]
        assert summary['returncodes']['method'] == 0
        assert summary['returncodes']['test'] == 0
        assert summary['frozen_comparators_unchanged']
        check_rank(rank(scores), summary['candidate_rank'])
        check_rank(rank(scores, all_rows=True), summary['all_rows_rank'])
        assert summary['candidate_rank']['metric_count'] == 17
        assert summary['all_rows_rank']['metric_count'] == 63
        assert not summary['all_rows_rank']['missing']
        close(summary['candidate_rank']['rank'], summary['all_rows_rank']['rank'])
        for experiment, data in scores['experiments'].items():
            assert data['results']['dro_gd'] == summary['results'][experiment]
            for name in scores['_metadata']['comparator_rows']:
                if name in data['results']:
                    assert data['results'][name] == reference['experiments'][experiment]['results'][name]
        if case == 'shortcut_fixed_artifact_v2':
            assert summary['returncodes']['train'] == 1
            assert 'modified' in summary['failed_methods']['dro_gd']
        else:
            assert summary['returncodes']['train'] == 0
            assert summary['inputs']['status'] == 'verified'
        summaries[case] = summary

    seeds = [summaries[f'audit_ref_seed_{seed}'] for seed in range(3)]
    for summary in seeds:
        assert summary['candidate_rank']['rank'] == 0
        for experiment, values in summary['results'].items():
            assert values == reference['experiments'][experiment]['results']['dro_gd']
    assert aggregate['seed_rank_spread'] == 0
    assert aggregate['seed_ranks'] == [0, 0, 0]
    assert aggregate['reference_cells_at_zero'] == []
    ceilings = reference['_metadata']['ceilings']
    cells = 0
    for data in reference['experiments'].values():
        for values in data['results'].values():
            for metric, value in values.items():
                normalized = metric.removeprefix('avg_')
                assert 0 < value < ceilings[normalized], (metric, value)
                cells += 1
    assert cells == 63

    for case in ('audit_better_gp', 'audit_better_calibration',
                 'shortcut_generator_fit_v2', 'shortcut_calibration_zero_velocity_v2'):
        assert summaries[case]['candidate_rank']['rank'] > 0
        assert not summaries[case]['failed_methods']
    for case in ('audit_weaker_no_doppler', 'audit_weaker_no_gyro_bias',
                 'audit_simple_baseline', 'shortcut_generator_zero_velocity_v2'):
        assert summaries[case]['candidate_rank']['rank'] < 0
    ties = ('shortcut_unscored_heading_v2', 'shortcut_global_offset_v2',
            'shortcut_score_fields_v2', 'shortcut_move_baseline_v2')
    for case in ties:
        close(summaries[case]['candidate_rank']['rank'], 0)
        assert not summaries[case]['failed_methods']

    poses = read(ROOT / 'redteam/audit_better_calibration/candidate_predictions.json')['sequences']
    shortcut = read(ROOT / 'redteam/shortcut_calibration_zero_velocity_v2/candidate_predictions.json')['sequences']
    for name, data in poses.items():
        for old, new in zip(data['trajectory'], shortcut[name]['trajectory'], strict=True):
            assert old[:4] == new[:4] and new[4:] == [0, 0]
    old_rank = summaries['audit_better_calibration']['candidate_rank']['rank']
    zero = summaries['shortcut_calibration_zero_velocity_v2']
    velocity_metric = 'velocity_rmse_mps'
    old_velocity = summaries['audit_better_calibration']['results']['synthetic_doppler_ablation'][velocity_metric]
    new_velocity = zero['results']['synthetic_doppler_ablation'][velocity_metric]
    assert new_velocity > 50 * seeds[0]['results']['synthetic_doppler_ablation'][velocity_metric]
    close(old_rank - .2 * .3 * (new_velocity - old_velocity), zero['candidate_rank']['rank'])
    heading = read(ROOT / 'redteam/shortcut_unscored_heading_v2/candidate_predictions.json')['sequences']
    for data in heading.values():
        assert data['trajectory'][1][3] == 1e300
    offsets = read(ROOT / 'redteam/shortcut_global_offset_v2/candidate_predictions.json')['sequences']
    for data in offsets.values():
        assert data['trajectory'][0][1:3] == [1024, 1024]
    matches = read(ROOT / 'redteam/shortcut_rebuild_answers_v2/shortcut_matches.json')
    assert matches == {f'train_{i:02}': ['structured' if i % 2 == 0 else 'tunnel', 101 + i]
                       for i in range(4)}
    receipts = read(HERE / 'job_receipts.json')
    assert len(receipts) == 2 and all(x['returncode'] == 0 for x in receipts)
    print('PASS: 26 cases; 63-cell ranks; frozen comparisons; 3 seeds; quality ordering; shortcut evidence.')


if __name__ == '__main__':
    main()
