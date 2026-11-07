"""Lightweight report verification; reads stored JSON, never runs inference."""
from pathlib import Path
import json
import math

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT/'redteam'


def clean(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: clean(v) for k,v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def load(path):
    return json.loads(path.read_text())


def main():
    reference = load(AUDIT/'reference_seed_0/scores_test.json')
    original = load(ROOT/'scoring/scores_test.json')
    config = load(ROOT/'scoring/reference.json')
    assert reference['experiments'] == original['experiments'], 'reference failed to reproduce stored test scores'
    summaries = {p.parent.name: load(p) for p in sorted(AUDIT.glob('*/summary.json'))}
    assert len(summaries) == 27, f'missing runs: {len(summaries)}'
    for name, d in summaries.items():
        assert (AUDIT/name/'run.sh').exists()
        assert (AUDIT/name/'method.py').exists()
        assert (AUDIT/name/'test.log').exists()
        if name != 'shortcut_empty':
            assert d['returncodes']['test'] == 0, name
            assert (AUDIT/name/'scores_test.json').exists(), name
            assert d['candidate_rank']['metric_count'] == 17
            assert d['all_rows_rank']['metric_count'] == 63
            assert not d['all_rows_rank']['missing']
        else:
            assert d['returncodes']['test'] == 1
    fixed = [summaries[f'reference_seed_{n}']['candidate_rank']['improvement'] for n in (0,1,2)]
    for n in (1,2):
        assert load(AUDIT/f'reference_seed_{n}/scores_test.json')['experiments'] == reference['experiments']
    scene_names = ['reference_seed_0','reference_data_seed_17','reference_data_seed_27']
    scene_ranks = [summaries[n]['candidate_rank']['improvement'] for n in scene_names]
    spread = max(scene_ranks)-min(scene_ranks)
    bounds = []
    for e, definition in config['experiments'].items():
        if e not in reference['experiments']: continue
        for method, metrics in reference['experiments'][e]['results'].items():
            for metric in definition['metrics']:
                value = metrics[metric]
                assert math.isfinite(value) and value >= 0
                if value == 0: bounds.append(f'{e}/{method}/{metric}')
    assert not bounds
    assert summaries['better_gp_alignment']['candidate_rank']['improvement'] > spread
    assert summaries['better_gp_alignment_temporal']['candidate_rank']['improvement'] > spread
    assert summaries['weaker_no_doppler']['candidate_rank']['improvement'] < -spread
    assert summaries['shortcut_comparison_compensation']['all_rows_rank']['improvement'] > spread
    assert summaries['shortcut_comparison_compensation']['candidate_rank']['improvement'] < 0
    paired_temporal = {str(seed): summaries[b]['candidate_rank']['improvement']-summaries[r]['candidate_rank']['improvement']
        for seed,b,r in [(7,'better_temporal','reference_seed_0'),
                         (17,'better_temporal_data_seed_17','reference_data_seed_17'),
                         (27,'better_temporal_data_seed_27','reference_data_seed_27')]}
    result = {'reference_matches_original_exactly': True,
              'fixed_data_seed_ranks': fixed, 'fixed_data_seed_spread': max(fixed)-min(fixed),
              'data_seed_ranks': dict(zip(['7','17','27'], scene_ranks)),
              'data_seed_rank_spread': spread,
              'paired_temporal_improvements': paired_temporal,
              'reference_metrics_at_bound': bounds,
              'scored_experiment_weight': sum(config['experiments'][e]['weight'] for e in reference['experiments']),
              'scored_candidate_metric_cells': 17, 'scored_all_method_metric_cells': 63,
              'runs': summaries}
    (AUDIT/'audit_results.json').write_text(json.dumps(clean(result), indent=2, allow_nan=False)+'\n')
    print('PASS: 27 runs, exact reference, 3 identical method seeds, strong quality ordering, complete finite-score coverage')
    print('Data-seed rank spread:', spread)
    print('Paired temporal gains:', paired_temporal)


if __name__ == '__main__':
    main()
