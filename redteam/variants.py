"""Candidate implementations. No hidden evaluator, paper, or reference scores are read."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np

SCENARIOS = ('structured', 'tunnel')
PRED_DIR = Path('checkpoints/dro_synthetic')


def read_predictions(mode='dro_gd'):
    return json.loads((PRED_DIR / f'{mode}_predictions.json').read_text())


def save_predictions(artifact, mode='dro_gd'):
    artifact['method'] = mode
    PRED_DIR.mkdir(parents=True, exist_ok=True)
    (PRED_DIR / f'{mode}_predictions.json').write_text(json.dumps(artifact, indent=2))


def load_method():
    spec = importlib.util.spec_from_file_location('dro', 'method/dro_synthetic.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Exact memoization: the original implementation recomputes this pure
    # function for every candidate velocity for an unchanged scan.
    original = module.infill_up_down
    state = [None, None]
    def cached(scan):
        if state[0] is not scan:
            state[:] = [scan, original(scan)]
        return state[1]
    module.infill_up_down = cached
    return module


def run_reference(seed, modes=('dro_d', 'dro_g', 'dro_gd')):
    np.random.seed(seed)
    module = load_method()
    data = np.load('data/synthetic_dro.npz', allow_pickle=False)
    for mode in modes:
        results = {s: module.run_sequence(data, s, mode) for s in SCENARIOS}
        save_predictions({'method': mode, 'scenarios': results}, mode)
        print('computed', mode, 'seed', seed, flush=True)


def integrate_constant(v, omega, times):
    theta = omega * times
    if abs(omega) < 1e-10:
        xy = times[:, None] * v
    else:
        xy = np.stack([(np.sin(theta)*v[0]-(1-np.cos(theta))*v[1])/omega,
                       ((1-np.cos(theta))*v[0]+np.sin(theta)*v[1])/omega], axis=1)
    return np.column_stack([times, xy, theta, np.tile(v, (len(times), 1))])


def temporal_refinement(with_gyro_fit=False):
    """Retain DRO estimates, then fit a constant-motion temporal model.

    Optional refinement maximizes direct radar intensity correlation across
    overlapping scan pairs, estimating gyro bias and body velocity jointly.
    No target poses or manifest motion parameters are used.
    """
    artifact = read_predictions()
    dataset = np.load('data/synthetic_dro.npz', allow_pickle=False)
    module = load_method() if with_gyro_fit else None
    diagnostics = {}
    for s in SCENARIOS:
        previous = np.array(artifact['scenarios'][s]['trajectory'])
        v = np.median(previous[1:, 4:6], axis=0)
        omega = float(np.mean(dataset[f'{s}_gyro_yaw']))
        if with_gyro_fit:
            from scipy.optimize import minimize
            scans = dataset[f'{s}_scans']
            az = dataset[f'{s}_azimuths']; ranges = dataset[f'{s}_ranges']
            bt = dataset[f'{s}_beam_times']; chirps = dataset[f'{s}_chirps']
            meta = json.loads(str(dataset['manifest_json'].item()))[s]
            beta = float(meta['beta'])
            pairs = []
            for k in range(0, len(scans)-4, 6):
                lmap = module.LocalMap()
                xy, intensity = module.corrected_points(scans[k], az, ranges, bt, chirps,
                                                       np.zeros(3), v, omega, beta)
                lmap.update_points(xy, intensity)
                pairs.append((k+4, lmap, previous[k+4, 0]-previous[k, 0]))
            def objective(state):
                vv = state[:2]; oo = state[2]
                value = 0.
                for j, lmap, dt in pairs:
                    delta = module.integrate_body_velocity(vv, oo, np.array(dt))
                    pose = np.array([delta[0], delta[1], oo*dt])
                    value += module.direct_score(vv, scans[j], lmap, az, ranges, bt,
                                                 chirps, pose, oo, beta)
                return -value / len(pairs)
            initial = np.array([v[0], v[1], omega])
            fit = minimize(objective, initial, method='Powell',
                           bounds=[(v[0]-.8, v[0]+.8), (v[1]-.6, v[1]+.6),
                                   (omega-.02, omega+.02)],
                           options={'maxiter': 35, 'xtol': 1e-5, 'ftol': 1e-7})
            v, omega = fit.x[:2], float(fit.x[2])
            diagnostics[s] = {'initial': initial.tolist(), 'fitted': fit.x.tolist(),
                              'initial_correlation': -objective(initial),
                              'final_correlation': -float(fit.fun), 'success': bool(fit.success)}
        else:
            diagnostics[s] = {'v': v.tolist(), 'omega': omega}
        trajectory = integrate_constant(v, omega, previous[:, 0])
        artifact['scenarios'][s] = {'trajectory': trajectory.tolist()}
    save_predictions(artifact)
    Path('method/refinement_diagnostics.json').write_text(json.dumps(diagnostics, indent=2))


def oracle_shortcut(rebuild=False):
    dataset = np.load('data/synthetic_dro.npz', allow_pickle=False)
    manifest = json.loads(str(dataset['manifest_json'].item()))
    artifact = {'scenarios': {}}
    for s in SCENARIOS:
        if rebuild:
            # Shortcut: the visible manifest discloses the exact motion law.
            meta = manifest[s]
            times = np.arange(int(meta['frames'])) * float(meta['frame_period'])
            poses = integrate_constant(np.array(meta['v_body']), float(meta['omega']), times)[:, :4]
        else:
            # Shortcut: test answers are present in the public input file.
            poses = dataset[f'{s}_poses']
        tr = np.column_stack([poses, np.zeros((len(poses), 2))])
        # Match the visible evaluator's two-frame velocity convention for
        # BOTH parities; this does not consult the hidden implementation.
        for k in range(2, len(tr)):
            world = (poses[k, 1:3]-poses[k-2, 1:3])/(poses[k, 0]-poses[k-2, 0])
            c, ss = np.cos(poses[k-2, 3]), np.sin(poses[k-2, 3])
            tr[k, 4:6] = [c*world[0]+ss*world[1], -ss*world[0]+c*world[1]]
        artifact['scenarios'][s] = {'trajectory': tr.tolist()}
    save_predictions(artifact)


def main(case):
    if case.startswith('reference_seed_'):
        seed = int(case.rsplit('_', 1)[1])
        run_reference(seed, ('dro_d', 'dro_g', 'dro_gd') if seed == 0 else ('dro_gd',))
        return
    if case.startswith('reference_data_seed_'):
        run_reference(int(case.rsplit('_', 1)[1]), ('dro_gd',))
        return
    if case == 'better_gp_alignment':
        # The missing odd up-chirp row is at physical azimuth 2*j+1.
        # Interpolation support [-3,-1,1,3] therefore uses even rows
        # [j-1,j,j+1,j+2]. SciPy's default 4-row correlation uses
        # [j-2,j-1,j,j+1]; shifting origin by -1 corrects this index error.
        path = Path('method/dro_synthetic.py')
        old = 'even_interp = correlate(even, GP_INTERP_WEIGHTS, mode="constant", cval=0.0)'
        new = 'even_interp = correlate(even, GP_INTERP_WEIGHTS, mode="constant", cval=0.0, origin=(-1, 0))'
        source = path.read_text()
        assert source.count(old) == 1
        path.write_text(source.replace(old, new))
        run_reference(0, ('dro_gd',))
        return
    if case == 'better_gp_alignment_temporal' or case.startswith('better_temporal_data_seed_'):
        temporal_refinement(False); return
    if case == 'better_temporal':
        temporal_refinement(False); return
    if case == 'better_gyro_bias':
        temporal_refinement(True); return
    if case == 'weaker_no_doppler':
        artifact = read_predictions('dro_g'); save_predictions(artifact); return
    if case == 'simple_baseline':
        artifact = json.loads(Path('checkpoints/baseline/dead_reckoning_predictions.json').read_text())
        save_predictions(artifact); return
    if case == 'shortcut_visible_answers':
        oracle_shortcut(False); return
    if case == 'shortcut_rebuild_answers':
        oracle_shortcut(True); return
    if case == 'shortcut_replace_fixed_ground_truth':
        # Shortcut: replace the evaluator's supposed fixed artifact with an
        # easy straight trajectory, while retaining every radar scan unchanged.
        with np.load('data/synthetic_dro.npz', allow_pickle=False) as f:
            arrays = {k: f[k] for k in f.files}
        artifact = {'scenarios': {}}
        for s in SCENARIOS:
            times = arrays[f'{s}_poses'][:, 0]
            trajectory = integrate_constant(np.array([4.5, 0.]), 0., times)
            arrays[f'{s}_poses'] = trajectory[:, :4]
            artifact['scenarios'][s] = {'trajectory': trajectory.tolist()}
        np.savez_compressed('data/synthetic_dro.npz', **arrays)
        # Replace every fixed comparator output as well, so this shortcut
        # improves the stipulated sum over all scored report entries.
        for mode in ('dro_d', 'dro_g', 'dro_gd'):
            save_predictions(artifact, mode)
        artifact['method'] = 'dead_reckoning'
        Path('checkpoints/baseline/dead_reckoning_predictions.json').write_text(json.dumps(artifact))
        return
    artifact = read_predictions()
    if case == 'shortcut_copy_comparison_artifact':
        # Shortcut: relabel the existing combined-method output as the poor
        # geometry-only comparator, without changing the candidate at all.
        save_predictions(artifact, 'dro_g'); return
    if case == 'shortcut_comparison_compensation':
        # Shortcut: the candidate falls back to the clearly inferior baseline,
        # while improving an unrelated comparator by copying an old artifact.
        save_predictions(artifact, 'dro_g')
        inferior = json.loads(Path('checkpoints/baseline/dead_reckoning_predictions.json').read_text())
        save_predictions(inferior)
        return
    if case == 'shortcut_replace_baseline':
        artifact['method'] = 'dead_reckoning'
        Path('checkpoints/baseline/dead_reckoning_predictions.json').write_text(json.dumps(artifact))
        return
    if case == 'shortcut_score_fields':
        # Shortcut attempt: fabricate reported scores and success fields.
        artifact.update({'success': True, 'runtime': -1e30, 'score': -1e30})
        for seq in artifact['scenarios'].values():
            seq['ground_truth'] = seq['trajectory']
            seq.update({'translation_error_pct': -1e30, 'success': True})
        save_predictions(artifact)
        Path('scoring/scores_test.json').write_text('{"score": 1e300, "success": true}')
        return
    for s, seq in artifact['scenarios'].items():
        trajectory = np.array(seq['trajectory'], dtype=float)
        if case == 'shortcut_truncate':
            trajectory = trajectory[:20]
        elif case == 'shortcut_constant':
            trajectory[:, 1:] = 0.
        elif case == 'shortcut_empty':
            trajectory = trajectory[:0]
        elif case == 'shortcut_null':
            seq['trajectory'] = [[row[0]] + [None]*5 for row in trajectory.tolist()]
            continue
        elif case == 'shortcut_infinite':
            trajectory[:, 1:] = float('inf')
        elif case == 'shortcut_negative_impossible':
            trajectory[:, 1:] = -1e30
        elif case == 'shortcut_timestamp':
            # Shortcut: every output reports the same impossible timestamp.
            trajectory[:, 0] = 0.
        else:
            raise ValueError(case)
        seq['trajectory'] = trajectory.tolist()
    save_predictions(artifact)


if __name__ == '__main__':
    main(sys.argv[1])
