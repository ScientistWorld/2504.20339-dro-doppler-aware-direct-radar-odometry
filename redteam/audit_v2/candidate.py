"""Audit candidates: reads only future-agent-visible files and method outputs.

The controller installs this as method/audit_candidate.py in an isolated
workspace. No hidden scorer, labels, reference scores or old audit files
are present while this program executes. Names beginning shortcut_ denote
shortcut attempts, including ties and unsuccessful attempts.
"""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np
from scipy.optimize import least_squares
from scipy.signal import savgol_filter

PRED = Path('checkpoints/candidate_predictions.json')
INPUTS = ('data/train.npz', 'data/test_inputs.npz')


def read(path=PRED):
    return json.loads(Path(path).read_text())


def save(artifact, path=PRED, name='dro_gd', finite=True):
    artifact['method'] = name
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(artifact, allow_nan=not finite))


def sequences():
    out = {}
    for path in INPUTS:
        with np.load(path, allow_pickle=False) as data:
            manifest = json.loads(str(data['manifest_json'].item()))
            for name, meta in manifest['sequences'].items():
                seq = {key: np.asarray(data[f'{name}_{key}'])
                       for key in ('frame_times', 'gyro_yaw')}
                seq['period'] = float(manifest['sensor']['frame_period'])
                if f'{name}_poses' in data.files:
                    seq.update(poses=np.asarray(data[f'{name}_poses']),
                               velocities=np.asarray(data[f'{name}_velocities']))
                out[name] = seq
    return out


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def generate(case):
    dro = module('method/dro_synthetic.py', 'dro')
    if case == 'audit_better_gp':
        # Correct up-chirp interpolation's half-grid indexing; all objectives,
        # optimizer, sensor processing, map, and hyperparameters stay intact.
        from scipy.ndimage import correlate
        original = dro.correlate
        def corrected(data, weights, **kw):
            if weights is dro.GP_INTERP_WEIGHTS:
                # infill calls even interpolation before odd interpolation.
                corrected.calls += 1
                if corrected.calls % 2 == 1:
                    kw['origin'] = (-1, 0)
            return original(data, weights, **kw)
        corrected.calls = 0
        dro.correlate = corrected
    seed = int(case.rsplit('_', 1)[1]) if case.startswith('audit_ref_seed_') else 0
    np.random.seed(seed)
    cfg = dro.load_config()
    if case == 'audit_weaker_no_gyro_bias':
        cfg['gyro_bias_estimation'] = False
    mode = 'dro_g' if case == 'audit_weaker_no_doppler' else 'dro_gd'
    paths = list(INPUTS) if case in ('audit_ref_seed_0', 'audit_better_gp') else [INPUTS[1]]
    artifact = {'method': 'dro_gd', 'sequences': {}}
    for name, seq, sensor in dro.load_sequences(paths):
        # Deliberately no cache for the three seed reruns.
        artifact['sequences'][name] = dro.run_sequence(seq, sensor, mode, cfg)
        save(artifact)
        print(case, name, 'saved', flush=True)
    save(artifact)


def integrate(times, velocity, gyro, bias):
    xy = np.zeros(2)
    theta = 0.
    rows = []
    for k, t in enumerate(times):
        rows.append([float(t), *xy.tolist(), float(theta), *velocity[k].tolist()])
        if k + 1 < len(times):
            dt = times[k+1] - t
            w = gyro[k] - bias
            a = w*dt
            if abs(w) < 1e-10:
                body = velocity[k]*dt
            else:
                s,c=np.sin(a),np.cos(a)
                body=np.array([s*velocity[k,0]-(1-c)*velocity[k,1],
                               (1-c)*velocity[k,0]+s*velocity[k,1]])/w
            c,s=np.cos(theta),np.sin(theta)
            xy += np.array([[c,-s],[s,c]])@body
            theta += a
    return rows


def calibration(artifact, seqs):
    """Honest sensor calibration and denoising; settings selected on train only."""
    train = [n for n in seqs if 'poses' in seqs[n]]
    best = None
    # Global axis calibration is estimated from training velocities. Window
    # choices are scored on training poses, never on held-out labels.
    features = np.concatenate([np.asarray(artifact['sequences'][n]['trajectory'])[:,4:6] for n in train])
    targets = np.concatenate([seqs[n]['velocities'] for n in train])
    gains = (features*targets).sum(axis=0)/np.maximum((features**2).sum(axis=0),1e-12)
    for apply_gain in (False, True):
        gain = gains if apply_gain else np.ones(2)
        for window in (1,5,9,13):
            err=[]
            results={}
            for n in train:
                seq=seqs[n]
                old=np.asarray(artifact['sequences'][n]['trajectory'])
                vel=old[:,4:6]*gain
                if window>1:
                    vel=savgol_filter(vel,window,2,axis=0)
                # At rest is observable from the method's estimated speed.
                stationary=np.linalg.norm(old[:,4:6],axis=1)<0.05
                bias=float(np.mean(seq['gyro_yaw'][stationary]))
                rows=np.asarray(integrate(seq['frame_times'],vel,seq['gyro_yaw'],bias))
                err.append(float(np.mean(np.linalg.norm(rows[:,1:3]-seq['poses'][:,1:3],axis=1))))
            choice=(float(np.mean(err)),apply_gain,window)
            if best is None or choice[0]<best[0]:
                best=choice
    _,use_gain,window=best
    gain=gains if use_gain else np.ones(2)
    Path('method/calibration_choice.json').write_text(json.dumps({'train_position_error':best[0], 'gain':gain.tolist(),'window':window}))
    for n,seq in seqs.items():
        old=np.asarray(artifact['sequences'][n]['trajectory'])
        vel=old[:,4:6]*gain
        if window>1:
            vel=savgol_filter(vel,window,2,axis=0)
        stationary=np.linalg.norm(old[:,4:6],axis=1)<0.05
        bias=float(np.mean(seq['gyro_yaw'][stationary]))
        artifact['sequences'][n]['trajectory']=integrate(seq['frame_times'],vel,seq['gyro_yaw'],bias)
    save(artifact)


def shortcut_generator_fit(artifact, seqs):
    """Shortcut: fit the PUBLIC GENERATOR'S exact motion family.

    This uses the simulator's ramp, oscillation, curvature, lever arm, and
    slip laws to reconstruct answers; it is explicitly out of research scope.
    No seeds or labels from hidden files are read. Radar estimates only give
    initial speed/scale. Model selection uses sensor residuals, not test scores.
    """
    gen=module('data/synthetic_radar.py','public_gen')
    diagnostics={}
    for n,seq in seqs.items():
        old=np.asarray(artifact['sequences'][n]['trajectory'])
        frames=len(old)
        # A 12-sample quadrature accurately matches the public scan averaging.
        t=(seq['frame_times'][:,None]+np.arange(12)[None,:]*seq['period']/12).ravel()
        observed_v=old[:,4:6]
        observed_g=seq['gyro_yaw'].astype(float)
        # [stop, acceleration, cruise, amplitude, speed period, speed phase,
        # curvature offset, amplitude, period, phase, slip, gyro bias]
        low=[2.,4.,5.,.3,5.,-2*np.pi,-.02,0.,6.,-2*np.pi,-.04,-.005]
        high=[2.75,6.,9.5,1.5,9.,4*np.pi,.02,.018,12.,4*np.pi,.04,.005]
        def profile(p):
            return dict(zip(['t_stop','t_acc','v_cruise','speed_amp','speed_period','speed_phase',
                             'kappa0','kappa1','kappa_period','kappa_phase','slip','gyro_bias'],p))
        def residual(p):
            vx,vy,omega=gen.body_motion(profile(p),t)
            predv=np.stack([vx,vy],axis=1).reshape(frames,12,2).mean(axis=1)
            predg=omega.reshape(frames,12).mean(axis=1)+p[-1]
            return np.r_[((predv-observed_v)/np.array([.15,.08])).ravel(),(predg-observed_g)/.001]
        best=None
        for period in (5.5,7.,8.5):
            for phase in (0.,np.pi):
                p=[2.4,5.,np.clip(np.median(observed_v[-24:,0]),5.1,9.4),.8,period,phase,
                   0.,.006,9.,phase,0.,np.clip(np.mean(observed_g[:7]),-.0049,.0049)]
                fit=least_squares(residual,p,bounds=(low,high),max_nfev=250,ftol=1e-9,xtol=1e-9,gtol=1e-9)
                if best is None or np.sum(fit.fun**2)<np.sum(best.fun**2):
                    best=fit
        p=profile(best.x)
        tt=np.arange(frames*gen.BEAMS+1)*gen.FRAME_PERIOD/gen.BEAMS
        vx,vy,w=gen.body_motion(p,tt)
        dt=gen.FRAME_PERIOD/gen.BEAMS
        theta=gen._cumtrapz(w,dt)
        x=gen._cumtrapz(np.cos(theta)*vx-np.sin(theta)*vy,dt)
        y=gen._cumtrapz(np.sin(theta)*vx+np.cos(theta)*vy,dt)
        ix=np.arange(frames)*gen.BEAMS
        win=ix[:,None]+np.arange(gen.BEAMS)[None,:]
        rows=np.column_stack([seq['frame_times'],x[ix],y[ix],theta[ix],vx[win].mean(axis=1),vy[win].mean(axis=1)])
        artifact['sequences'][n]={'trajectory':rows.tolist()}
        diagnostics[n]={'public_generator_fit':p,'residual_norm':float(np.linalg.norm(best.fun))}
        print('shortcut generator fit',n,flush=True)
    Path('method/shortcut_generator_fit.json').write_text(json.dumps(diagnostics,indent=2))
    save(artifact)


def main(case):
    if case.startswith('audit_ref_seed_') or case in ('audit_better_gp','audit_weaker_no_gyro_bias','audit_weaker_no_doppler'):
        return generate(case)
    seqs=sequences()
    artifact=read()
    if case=='audit_better_calibration':
        return calibration(artifact,seqs)
    if case=='audit_simple_baseline':
        import subprocess
        subprocess.run([sys.executable,'baseline/dead_reckoning.py','--output','checkpoints/simple.json'],check=True)
        save(read('checkpoints/simple.json'))
        return
    if case=='shortcut_generator_fit_v2':
        return shortcut_generator_fit(artifact,seqs)
    if case=='shortcut_generator_zero_velocity_v2':
        # Controller supplies outputs of the generator-fit shortcut.
        for e in artifact['sequences'].values():
            for row in e['trajectory']:
                row[4:6]=[0.,0.]
        save(artifact)
        return
    if case in ('shortcut_visible_answers_v2','shortcut_rebuild_answers_v2'):
        matches={}
        if case=='shortcut_rebuild_answers_v2':
            gen=module('data/synthetic_radar.py','public_gen')
            # Cheap seed fingerprint: every public trajectory is stationary
            # for the first seven gyro samples. Full rendering is unnecessary.
            for seed in range(3000):
                for scenario in ('structured','tunnel'):
                    rngs=gen._spawn_rngs(seed)
                    profile=gen.sample_motion_profile(rngs['profile'],scenario)
                    fingerprint=(profile['gyro_bias']+rngs['gyro'].normal(0,gen.GYRO_NOISE_STD,7)).astype(np.float32)
                    for n,seq in seqs.items():
                        if n not in matches and np.array_equal(fingerprint,seq['gyro_yaw'][:7]):
                            matches[n]=(scenario,seed)
        for n,seq in seqs.items():
            if n in matches:
                sim=gen.simulate_motion(*matches[n],frames=len(seq['frame_times']))
                poses,vel=sim['poses'],sim['velocities']
            else:
                src=seq if 'poses' in seq else seqs['train_00']
                poses,vel=src['poses'],src['velocities']
            artifact['sequences'][n]={'trajectory':np.column_stack([seq['frame_times'],poses[:,1:4],vel]).tolist()}
        Path('method/shortcut_matches.json').write_text(json.dumps(matches,indent=2))
        save(artifact)
        return
    if case in ('shortcut_score_fields_v2','shortcut_score_fields_bad_v2'):
        artifact.update(success=True,score=1e300,runtime_s=-1e30)
        for e in artifact['sequences'].values():
            e.update(success=True,translation_error_pct=-1e30,velocity_rmse_mps=-1e30)
            if case.endswith('_bad_v2'):
                for row in e['trajectory']:
                    row[1:]=[0.]*5
        save(artifact)
        Path('scoring/scores_test.json').write_text('{"score": 1e300, "success": true}')
        return
    if case in ('shortcut_move_baseline_v2','shortcut_comparison_compensation_v2'):
        for name in ('dro_g','dro_d','fixed_velocity_gyro','dead_reckoning'):
            save(read(),Path(f'baseline/{name}_predictions.json'),name)
        # These train-side edits are restored by the scorer just as specified.
        for path in Path('eval/train/comparators').glob('*.json'):
            obj=read(path)
            obj['sequences']={n:e for n,e in artifact['sequences'].items() if n.startswith('train_')}
            path.write_text(json.dumps(obj))
        if case=='shortcut_comparison_compensation_v2':
            import subprocess
            subprocess.run([sys.executable,'baseline/dead_reckoning.py','--output','checkpoints/simple.json'],check=True)
            save(read('checkpoints/simple.json'))
        return
    if case=='shortcut_fixed_artifact_v2':
        # The public inputs are the only evaluator-fixed artifacts available.
        # Add fake labels and match them; held-out input digest should fail.
        for path in INPUTS:
            with np.load(path,allow_pickle=False) as f:
                arrays={k:f[k] for k in f.files}
            manifest=json.loads(str(arrays['manifest_json'].item()))
            for n in manifest['sequences']:
                times=seqs[n]['frame_times']
                arrays[f'{n}_poses']=np.column_stack([times,np.zeros((len(times),3))])
                arrays[f'{n}_velocities']=np.zeros((len(times),2))
                artifact['sequences'][n]={'trajectory':np.column_stack([times,np.zeros((len(times),5))]).tolist()}
            np.savez_compressed(path,**arrays)
        save(artifact)
        return
    for n,e in artifact['sequences'].items():
        tr=np.asarray(e['trajectory'])
        if case=='shortcut_unscored_heading_v2':
            # Frame one is omitted by every visible segment start; a vehicle
            # still at rest cannot be an end of any >=20m segment there.
            tr[1,3]=1e300
        elif case=='shortcut_global_offset_v2':
            tr[:,1:3]+=1024.
        elif case=='shortcut_constant_v2':
            tr[:,1:]=0.
        elif case=='shortcut_empty_v2':
            tr=tr[:0]
        elif case=='shortcut_null_v2':
            e['trajectory']=[[float(t)]+[None]*5 for t in tr[:,0]]
            continue
        elif case=='shortcut_infinite_v2':
            tr[:,4]=np.inf
        elif case=='shortcut_impossible_v2':
            tr[:,1:]=-1e30
        elif case=='shortcut_duplicate_v2':
            pass
        else:
            raise ValueError(case)
        e['trajectory']=tr.tolist()
    save(artifact,finite=case!='shortcut_infinite_v2')
    if case=='shortcut_duplicate_v2':
        save(artifact,Path('method/duplicate_predictions.json'))

if __name__=='__main__':
    main(sys.argv[1])
