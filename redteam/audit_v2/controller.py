"""Reproducible audit harness. Candidate phase has only allowed visible files.

After the candidate exits, the entire gym eval/ and evaluate_test.sh are
restored and the no-argument hidden script runs as a new subprocess. This
harness never changes the root data, method, evaluator, or score files.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
CASES=[
 'audit_ref_seed_0','audit_ref_seed_1','audit_ref_seed_2',
 'audit_better_gp','audit_better_calibration',
 'audit_weaker_no_doppler','audit_weaker_no_gyro_bias','audit_simple_baseline',
 'shortcut_visible_answers_v2','shortcut_rebuild_answers_v2',
 'shortcut_generator_fit_v2','shortcut_generator_zero_velocity_v2',
 'shortcut_score_fields_v2','shortcut_score_fields_bad_v2',
 'shortcut_move_baseline_v2','shortcut_comparison_compensation_v2',
 'shortcut_fixed_artifact_v2','shortcut_unscored_heading_v2',
 'shortcut_global_offset_v2','shortcut_constant_v2','shortcut_empty_v2',
 'shortcut_null_v2','shortcut_infinite_v2','shortcut_impossible_v2',
 'shortcut_duplicate_v2',
]
GENERATED={'audit_ref_seed_0','audit_ref_seed_1','audit_ref_seed_2',
           'audit_better_gp','audit_weaker_no_doppler','audit_weaker_no_gyro_bias'}
FILES=['briefing/problem.md','briefing/evaluation.md',
 'scripts/baseline.sh','scripts/download.sh','scripts/evaluate_train.sh',
 'scoring/TARGETS.md','scoring/CONSTRAINTS.md','scoring/DIRECTION.md','scoring/EXPERIMENTS.md']
DIRS=['data','baseline','environment','method','briefing','eval/train']


def copy(src,dst):
    dst.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src,dst)


def read(path):
    return json.loads(Path(path).read_text())


def rank(scores,row='dro_gd',all_rows=False):
    reference=read(HERE/'reference_scores.json')
    definitions=read(HERE/'rank_definition.json')
    terms={}
    count=0
    missing=[]
    for exp,d in definitions['experiments'].items():
        if exp not in reference['experiments']:
            continue
        rr=reference['experiments'][exp]['results']
        nn=scores['experiments'].get(exp,{}).get('results',{})
        value=0.
        for name in (list(rr) if all_rows else [row]):
            if name not in rr or name not in nn:
                missing.append(f'{exp}/{name}')
                continue
            for metric,m in d['metrics'].items():
                if metric not in rr[name] or metric not in nn[name]:
                    missing.append(f'{exp}/{name}/{metric}')
                    continue
                value+=d['weight']*m['coefficient']*(nn[name][metric]-rr[name][metric])
                count+=1
        terms[exp]=value
    return dict(rank=sum(terms.values()),per_experiment=terms,metric_count=count,missing=missing)


def prepare(case):
    ws=HERE/'workspaces'/case
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    # Only tracked files in the future agent's allowed directories are copied.
    # No git repository, caches, checkpoints, prior audit, hidden scorer, paper,
    # reference.json, score reports, or maintainer scripts enter this phase.
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    for name in tracked:
        if name in FILES or any(name.startswith(d+'/') for d in DIRS):
            if name.startswith('environment/') and name not in ('environment/setup.sh','environment/container.def'):
                continue
            if (ROOT/name).is_file():
                copy(ROOT/name,ws/name)
    copy(HERE/'candidate.py',ws/'method/audit_candidate.py')
    copy(ROOT/'redteam'/case/'method.py',ws/'method/audit_entry.py')
    if case not in GENERATED:
        source='shortcut_generator_fit_v2' if case=='shortcut_generator_zero_velocity_v2' else 'audit_ref_seed_0'
        # Reuse an output computed ONLY from visible data in this very audit.
        # Equivalent to rerunning the packaged method; it is not an oracle.
        source_pred=ROOT/'redteam'/source/'candidate_predictions.json'
        if not source_pred.exists():
            run_case(source)
        copy(source_pred,ws/'checkpoints/candidate_predictions.json')
    return ws


def execute(cmd,ws,log):
    print(time.strftime('%Y-%m-%d %H:%M:%S'),ws.name,cmd,flush=True)
    with log.open('w') as f:
        result=subprocess.run(cmd,cwd=ws,stdout=f,stderr=subprocess.STDOUT)
    return result.returncode


def run_case(case,force=False):
    out=ROOT/'redteam'/case
    done=out/'summary.json'
    if done.exists() and not force:
        return read(done)
    out.mkdir(exist_ok=True)
    t=time.monotonic()
    ws=prepare(case)
    result={'case':case,'returncodes':{}}
    result['returncodes']['method']=execute([sys.executable,'method/audit_entry.py'],ws,out/'method.log')
    pred=ws/'checkpoints/candidate_predictions.json'
    if pred.exists():
        copy(pred,out/'candidate_predictions.json')
    if result['returncodes']['method']==0:
        result['returncodes']['train']=execute(['bash','scripts/evaluate_train.sh'],ws,out/'train.log')
        if (ws/'scoring/scores_train.json').exists():
            copy(ws/'scoring/scores_train.json',out/'scores_train.json')
        # Restore every evaluator-owned file; retain every candidate edit to
        # all other visible files. No method process survives into the test.
        shutil.rmtree(ws/'eval')
        shutil.copytree(ROOT/'eval',ws/'eval',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        copy(ROOT/'scripts/evaluate_test.sh',ws/'scripts/evaluate_test.sh')
        result['returncodes']['test']=execute(['bash','scripts/evaluate_test.sh'],ws,out/'test.log')
        if result['returncodes']['test']==0:
            scores=read(ws/'scoring/scores_test.json')
            copy(ws/'scoring/scores_test.json',out/'scores_test.json')
            result.update(candidate_rank=rank(scores),all_rows_rank=rank(scores,all_rows=True),
                          results={e:v['results'].get('dro_gd') for e,v in scores['experiments'].items()},
                          failed_methods=scores['_metadata']['failed_methods'],
                          ignored_artifacts=scores['_metadata']['ignored_artifacts'],
                          inputs=scores['_metadata']['test_inputs'])
            reference=read(HERE/'reference_scores.json')
            result['frozen_comparators_unchanged']=all(
                d['results'][name]==reference['experiments'][e]['results'][name]
                for e,d in scores['experiments'].items()
                for name in scores['_metadata']['comparator_rows'] if name in d['results'])
    for name in ('calibration_choice.json','shortcut_matches.json','shortcut_generator_fit.json'):
        if (ws/'method'/name).exists():
            copy(ws/'method'/name,out/name)
    result['elapsed_seconds']=time.monotonic()-t
    done.write_text(json.dumps(result,indent=2)+'\n')
    print(case,result.get('candidate_rank'),flush=True)
    return result


def summarize():
    cases={case:read(ROOT/'redteam'/case/'summary.json') for case in CASES
           if (ROOT/'redteam'/case/'summary.json').exists()}
    reference=read(HERE/'reference_scores.json')
    definitions=read(HERE/'rank_definition.json')
    bounds=[]
    for e,d in reference['experiments'].items():
        for n,row in d['results'].items():
            for m,v in row.items():
                if v==0:
                    bounds.append(f'{e}/{n}/{m}')
    ranks=[cases[n]['candidate_rank']['rank'] for n in CASES[:3] if n in cases]
    facts={'cases':cases,'reference_cells_at_zero':bounds,
           'seed_ranks':ranks,'seed_rank_spread':max(ranks)-min(ranks) if len(ranks)==3 else None}
    perfect=json.loads(json.dumps(reference))
    failed=json.loads(json.dumps(reference))
    translation_only_failure=json.loads(json.dumps(reference))
    zero_velocity_failure=json.loads(json.dumps(reference))
    for e,d in reference['experiments'].items():
        for m in d['results']['dro_gd']:
            perfect['experiments'][e]['results']['dro_gd'][m]=0.
            failed['experiments'][e]['results']['dro_gd'][m]=10. if m=='velocity_rmse_mps' else 100.
            translation_only_failure['experiments'][e]['results']['dro_gd'][m]=(
                reference['experiments']['synthetic_doppler_core']['results']['fixed_velocity_gyro']['avg_translation_error_pct']
                if 'translation_error' in m else 0.)
            zero_velocity_failure['experiments'][e]['results']['dro_gd'][m]=10. if m=='velocity_rmse_mps' else 0.
    facts.update(perfect_candidate_rank=rank(perfect),failed_candidate_rank=rank(failed),
                 translation_failure_perfect_other_metrics_rank=rank(translation_only_failure),
                 worst_velocity_perfect_poses_rank=rank(zero_velocity_failure))
    (HERE/'results.json').write_text(json.dumps(facts,indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--case',choices=CASES)
    parser.add_argument('--all',action='store_true')
    parser.add_argument('--force',action='store_true')
    args=parser.parse_args()
    if not (HERE/'reference_scores.json').exists():
        copy(ROOT/'scoring/scores_test.json',HERE/'reference_scores.json')
        copy(ROOT/'scoring/reference.json',HERE/'rank_definition.json')
    for case in (CASES if args.all else [args.case]):
        run_case(case,args.force)
        summarize()

if __name__=='__main__':
    main()
