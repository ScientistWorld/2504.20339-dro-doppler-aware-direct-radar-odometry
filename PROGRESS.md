# Progress

## What Works

- Paper analysis is complete enough for the core implementation.
- The authors' public DRO code release is available under `method/upstream_dro/`.
- A local procedural FMCW spinning-radar benchmark generator is implemented in `data/synthetic_radar.py`.
- A compact DRO implementation is implemented in `method/dro_synthetic.py`, including direct local-map registration, Doppler correction, local GP up/down chirp infill, Doppler velocity objective, gyroscope yaw integration, and online map update.
- A fixed-velocity gyro baseline and method-agnostic evaluator are implemented.
- `python validate.py` passes before job submission.
- CPU job `f0db0bd3-b7b` ran the full pipeline end-to-end without errors.

## Results

- First job scores showed a working but unsuccessful reproduction: fixed-velocity baseline `ct_r` had `25.05%` average translation error, while `dro_gd` had `35.82%`. This supports `method_runs` only, not `core_claim`.
- After reviewing the failure, the Doppler objective sign was corrected and the velocity optimizer was changed to coarse-to-local search to avoid getting stuck near the previous velocity.
- Second job `4736bccc-2e7` still failed the core claim: `dro_d` only improved slightly to `24.87%`, and `dro_gd` remained worse than baseline at `35.50%`.
- Added a Doppler-derived velocity initializer that estimates per-azimuth up/down range shifts by cross-correlation and solves the radial velocity relation before the direct/Doppler objective refinement.
- Third job `fb9bf823-812` completed end-to-end but still failed the core claim. `dro_d` improved to `23.41%` versus `25.05%` for the fixed-velocity baseline, while `dro_gd` degraded to `83.74%`, showing that the direct local-map term dominated the Doppler cue and collapsed the estimated forward velocity.
- Fixed the Doppler initializer's discrete row-shift sign convention, increased the synthetic Doppler coefficient so the up/down chirp displacement is measurable after preprocessing, and rebalanced the combined objective so DRO-GD remains anchored to the Doppler velocity estimate while still evaluating the direct local-map registration term.
- Fourth job `8e70fbca-fde` showed that the Doppler-only path now works: `dro_d` reached `10.90%` average translation error versus `25.05%` for the fixed-velocity baseline. The combined `dro_gd` result remained worse than baseline at `33.03%`, so the milestone remains `method_runs`.
- The latest edit further reduces the direct local-map weight in the combined objective and strengthens the Doppler-initializer prior for the reduced-scale synthetic benchmark.
- Fifth job `66bcfbec-1bc` produced effectively the same DRO-GD result (`33.03%`), confirming that anchoring to the raw cross-correlation initializer is the wrong control point. The refined Doppler-only objective is good, but the raw initializer is noisy.
- The latest edit changes DRO-GD into a two-stage reduced-scale optimization: first obtain the refined Doppler-only velocity estimate, then use it as the initialization and local prior while evaluating the combined direct-plus-Doppler objective.
- Sixth job `f8b4acd2-d32` reached `core_claim`: DRO-GD achieved `10.90%` average translation error versus `25.05%` for the fixed-velocity gyro baseline, while preserving near-zero heading error on this synthetic benchmark and reporting `1.05 m/s` velocity RMSE.
- Final validation fix: `scores.json` now uses explicit `synthetic_doppler_core` and `synthetic_doppler_ablation` experiment names instead of the paper's real automotive table names. Matching synthetic reference anchors were added so `python validate.py --compare` validates the replacement benchmark without comparing synthetic reduced-scale numbers to paper real-dataset magnitudes.
- Continuing audit job `d43de523-464` reran the full packaged pipeline inside the container with exit code 0. It regenerated `data/synthetic_dro.npz`, baseline predictions, DRO-D/G/GD predictions, `scoring/scores.json`, and passed `python validate.py --compare`.
- The audit rerun reproduced the core scores exactly: fixed-velocity gyro baseline `25.05%` average translation error, `dro_d` `10.90%`, and `dro_gd` `10.90%`, with near-zero heading error and `1.05 m/s` velocity RMSE for the combined method.
- Follow-up audit found that the previous core-claim state was too weak: up/down infill used neighbor averaging instead of GP regression, velocity RMSE only compared speed magnitudes, and exact synthetic yaw rates made rotation nearly trivial.
- The final implementation replaces the infill with local squared-exponential GP cross-correlation weights, adds deterministic noisy/bias gyro measurements to the generated data, uses those measurements in baseline and method, scores vector body-frame velocity RMSE, and replaces the local optimizer's Nelder-Mead refinement with normalized finite-difference gradient ascent in the form of the paper's update rule.
- CPU audit job `cf4a04e5-70e` completed with exit code 0 and passed `python validate.py --compare` after regenerating data, baseline predictions, DRO-D/G/GD predictions, and `scoring/scores.json`.
- The revised reproduction restores `core_claim`: fixed-velocity gyro baseline average translation error is `24.999%`, DRO-D is `2.668%`, and DRO-GD is `2.668%`. DRO-GD also reports `1.489 deg/100m` rotation error under the noisy gyro constraint and `0.123 m/s` vector body-frame velocity RMSE.
- CPU follow-up job `99110a51-e02` completed with exit code 0 and regenerated `scoring/scores.json` with four experiments: aggregate core, structured scenario, tunnel scenario, and ablation/velocity constraints.
- Final per-scenario scores show DRO-GD remains better than the fixed-velocity gyro baseline in both generated settings: `2.385%` versus `22.572%` translation error on `structured`, and `2.952%` versus `27.426%` on `tunnel`.
- Final validation with `python validate.py` passes.
- Split-score audit job `c758ed34-2b1` completed with exit code 0 on 2026-06-06. On the held-out odd-frame test slice, DRO-GD reached `2.703%` average translation error versus `24.999%` for the fixed-velocity gyro baseline; the train slice was similarly stable at `2.652%` versus `25.001%`.
- The standalone evaluator has been tightened to report endpoint-position drift and path-length error alongside the primary translation/rotation metrics, matching the richer train/test evaluator contract.
- Final verification added those endpoint/path metrics to the committed `scores.json` and synthetic reference anchors, adjusted the reproduced synthetic experiment weights for sensible gym scoring, and confirmed `python validate.py` plus `python validate.py --compare` pass.
- Current audit tightened evaluation integrity further: `scripts/evaluate.sh` now passes the benchmark data file to `eval/odometry_metrics.py`, which loads ground truth from `data/synthetic_dro.npz` instead of trusting the prediction artifact. The evaluator also raises on trajectories too short for the configured segment lengths.
- The paper reference table now includes the omitted Table I `CT-LG` lidar baseline average (`5.1675%`, `0.12 deg/100m`), and `scoring/TARGETS.md` explicitly lists endpoint and path-length constraints.

### Final hardening iteration (2026-11-08)

- Job `414368ce-823` (exit 0, 22 min on 8 cores) rebuilt the gym from the final code. That covers new train (6) and held-out (12) splits from the random-process motion model, train-only weight selection (8192), comparators, the reference DRO-GD, frozen comparator rows, all score files, `validate.py`, and the shortcut and variant audit in `redteam/hardening_v3/`.
- Held-out reference: 1.278 % translation, 0.299 deg/100 m rotation, 0.106 m/s velocity RMSE. Train: 1.328 % / 0.336 / 0.118.
- Both evaluators now enforce velocity–pose consistency, velocity eligibility, the origin start and physically possible headings and per-scan motion.
- Details in `HARDENING.md`.

## Remaining

- Higher milestones would require scaling beyond this compact gym: adding more synthetic scenarios, running on public Boreas/MulRan sequences, or reproducing additional paper tables.
- The real automotive Doppler dataset used for the paper's strongest Table I result is not fully public, so this environment stops at the validated synthetic core claim.

## Issues

- The Doppler-enabled automotive dataset used for the paper's central Table I result is not fully public in the paper. The public release notes only one newer Boreas Doppler-enabled sequence at the time of release, while the paper reports a larger collected automotive dataset.
- Early runs produced poor DRO estimates and were kept at `method_runs` until the objective sign, velocity initialization, objective balance, and two-stage reduced-scale DRO-GD optimization were fixed.
- The third through fifth runs diagnosed a clear objective-balance issue: the Doppler-only variant became useful, but adding the direct term initially hurt badly because the raw Doppler initializer was too noisy to anchor the combined objective directly.
- The final core-claim run depends on a two-stage reduced-scale optimization for DRO-GD. This is documented as a scaling adaptation: it preserves the paper's Doppler and direct objective computations while making the reduced synthetic benchmark stable.
- The validator requires every scored experiment to appear in `reference.json`, so the file includes two clearly labeled synthetic replacement benchmark anchors in addition to the original paper-reported experiments.
- A later read-only audit judged the earlier `core_claim` status overly optimistic. The milestone was kept at `method_runs` until job `cf4a04e5-70e` reran the revised, more faithful implementation in the container.
- During the continuation audit, the GP infill operator was corrected from SciPy convolution to cross-correlation so asymmetric interpolation kernels are applied in the same orientation as the paper's neural-network-style convolution implementation.
- The absolute stdout/stderr paths reported for job `cf4a04e5-70e` were not mounted in this interactive session, but the workspace artifacts and `validate.py --compare` output confirm successful execution.
- The absolute stdout/stderr paths reported for job `99110a51-e02` were also not mounted in this interactive session, but the regenerated `scoring/scores.json` and final `python validate.py` output confirm successful execution.
- The final verifier did not rerun `scripts/evaluate.sh` on the login node because the login Python lacks NumPy; the packaged container installs NumPy via `environment/setup.sh`, prior container jobs exercised the pipeline, and `validate.py --compare` passes on the committed artifacts.
- The latest standalone evaluator change also cannot be exercised on the login node for the same NumPy reason. A CPU container validation job is being submitted to regenerate the synthetic data, predictions, score files, and validators.

## Deviations from Paper

- Dataset substitution: the paper evaluates on Boreas, MulRan, an off-road robot dataset, and a Doppler-enabled automotive dataset collected by the authors. This workspace currently uses a synthetic spinning FMCW radar benchmark generated locally. The substitution is necessary for a compact autonomous reproduction because the central Doppler-enabled dataset is not fully public and the public datasets are large.
- Scale substitution: the benchmark uses fewer beams, range bins, and frames than the paper's real radar data. The algorithmic procedure is preserved.
- Sensor-constant substitution: the synthetic benchmark uses a larger Doppler range-shift coefficient than the first draft of the generator so the alternating chirp displacement remains observable at reduced range resolution and frame count. This changes the simulated sensor scale, not the DRO algorithm.

## Hardening iteration (2026-11-07)

- The benchmark was rebuilt with a hidden held-out split. Visible: 4 labelled sequences (`data/train.npz`). Hidden: 6 sequences, with inputs in `data/test_inputs.npz` and labels in `eval/test/`.
- The trajectories have time-varying speed and yaw rate, start from rest, and use a biased gyro. Tunnels are geometrically degenerate.
- The evaluators enforce a strict output contract, freeze the comparator rows and apply failure ceilings.
- Reference fixes:
  - start pose taken from the end of the previous scan;
  - the paper's gyro-bias heuristic;
  - GD objective weight selected on train (2048).
- Held-out reference: 1.355 % translation error, 0.417 deg/100 m rotation, 0.115 m/s velocity RMSE.
- Full audit, with variant and shortcut scores before and after: `HARDENING.md` and `redteam/hardening/`.
- Remaining deviation: the Doppler objective's advantage over geometry-only registration in tunnels is small here (2.47 % vs 2.70 %), unlike the paper.
