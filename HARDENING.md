# Hardening report (final iteration)

**Bottom line.** Better results now score higher and worse results lower, with every gap measured on paired held-out sequences. The two shortcuts that paid in `REDTEAM.md` are closed:

- **Zero velocity with calibrated poses:** +0.024 → scored as failed.
- **Fitting the generator's motion family:** +0.059 → −6.13.

The two contract ties (an impossible heading on a stationary scan, a global position offset) now fail. All other shortcuts still fail or change nothing.

The held-out test doubled to 12 sequences. The motion model no longer has a low-dimensional closed form. Velocity must agree with the reported poses and must beat dead reckoning. The reference was rebuilt from the final code, which includes a fix to its Doppler infill.

**How ranks are computed.** Each rank is `Σ_exp weight × Σ_metric coefficient × (candidate − reference)`. It uses the `dro_gd` row against the reference report `scoring/scores_test.json`, with the weights and signed coefficients of `scoring/reference.json`. The reference ranks 0, and positive means better.

**Noise.** "± SE" and "95 % CI" come from a paired, scene-stratified bootstrap over the 12 held-out sequences (4000 resamples). Candidate and reference always see the same resampled sequences.

**Evidence.** Everything is in `redteam/hardening_v3/` (`job.sh`, `audit.py`):
- `results.json`: all ranks, bootstrap statistics, per-sequence metrics and the paper-effect table;
- `cases/<case>/`: the hidden-test report, train report (honest variants), logs and summary for each case.

Every case ran `bash scripts/evaluate_test.sh` with **no arguments**, in a fresh mini workspace holding only the hidden evaluator, the test inputs and the candidate (job `414368ce-823`, exit 0).

## 1. What changed

| Problem | Fix |
|---|---|
| **Zero-velocity shortcut** (REDTEAM, +0.024): calibrated poses plus all-zero velocities outranked the reference, because pose gains paid for the velocity penalty | Both evaluators now fail a method if its reported body velocities do not describe its own poses. For each scan, the pose change to the next scan (expressed at the mid-scan heading, divided by the scan period) must match the reported velocity, with RMS gap ≤ 0.5 m/s per sequence. Honest outputs sit at ≤ 0.001 m/s: ground truth 0.0010, reference, comparators and all honest variants 0.0003. A second eligibility rule: velocity RMSE must beat the frozen dead-reckoning row, like translation already had to. |
| **Generator-fit shortcut** (+0.059): every public trajectory was a 12-parameter closed-form motion (smoothstep ramp × sinusoidal speed, sinusoidal curvature, constant slip), which the redteam fitted to gyro and radar velocities and reintegrated | `data/synthetic_radar.py` now drives speed, curvature and side slip with smooth random processes: Gaussian-filtered white noise on a 0.05 s grid, correlation times 0.8–2 s. A drive is no longer a member of a low-dimensional family. Train and test were regenerated with the same generator; the test seeds are new 62-bit values that exist only in `eval/test/make_test_set.py`. `scoring/CONSTRAINTS.md` names fitting or rendering the generator's motion or scene model as invalid. |
| **Impossible heading tie** (1e300 heading on a stationary scan that no segment touches) | Headings with \|θ\| > 1000 rad fail. Heading changes between scans faster than 2 rad/s fail. Position jumps faster than 100 m/s fail. |
| **Global-offset tie** (+1024 m everywhere; the metrics are invariant to frame changes) | The first pose must be the origin with heading 0 (1 mm / 1 mrad). A new probe, the whole trajectory rotated by 0.3 rad, fails the same rule. |
| Small held-out test: 6 sequences, and the redteam's GP-alignment improvement was within noise | 12 held-out sequences (6 landmark-rich, 6 tunnel) and 6 train sequences (previously 4). Shuffled names do not reveal the scene type. |
| **Reproduction bug** in the reference's GP infill (found by the redteam) | The up-chirp interpolated rows were inferred two raw rows (4°) away from where they were placed. scipy centres the 4-tap kernel on tap 2, and the call is now made with `origin=(-1, 0)`; the down-chirp rows were already correct. This is a fix to the paper's infill step, not a change of method, so it is now in the reference. The previous behaviour is kept as the weaker variant `weaker_legacy_gp_infill`. |
| Combined-objective weight: the earlier selection sat at the edge of its grid (2048) | Re-selected on the new train split over 128 / 512 / 2048 / 8192 (train TE 2.02 / 1.52 / 1.37 / 1.33 %). 8192 is selected, again at the edge, but the curve has flattened (−0.05 points per ×4). |
| Sensor metadata | The manifest now carries `radar_ahead_of_rear_axle_m` (1.2 m), the extrinsic the paper uses for its non-slip lateral-velocity correction. |

**What stays as before:**
- labels live only in `eval/test/`, and the test-input digest is checked;
- comparator rows are frozen in `eval/{train,test}/comparators/`;
- reserved names are ignored and duplicate names fail;
- malformed output and the translation-eligibility rule score at the ceilings.

`eval/train/` and `eval/test/` still share no code. Both evaluators enforce identical rules.

**Reruns.** The reference, the three comparators and every score file were regenerated from the final code (job `414368ce-823`):
- `scoring/scores_test.json` and `scores_train.json` hold only the reference and the frozen rows;
- `python validate.py` passes.

## 2. Do better results score higher? (variants, before → after)

"Before" is the redteam's run on the old gym (6 held-out sequences, old reference). "After" is this gym. Train ranks are against `scoring/scores_train.json`.

| Variant | Before | After: test rank | ± SE, 95 % CI | Sequences better / worse | After: train rank |
|---|---:|---:|---|---|---:|
| Reference DRO-GD | 0 | **0** | — | — | 0 |
| Train-selected calibration: velocity gains [1.012, 0.397], 9-scan Savitzky–Golay smoothing | +0.384 | **+0.303** | ± 0.050, [+0.199, +0.394] | 6 / 6 | +0.251 |
| GP infill alignment fix (redteam's "better" variant) | +0.029 (within noise) | now in the reference: the old behaviour scores **−0.0127** | ± 0.0051, [−0.0237, −0.0037] | 4 / 8 | — |
| Smoothing only (window chosen on train) | — | −0.010 | ± 0.010, [−0.031, +0.009] | 5 / 7 | +0.013 |
| Remove Doppler objective (DRO-G) | −0.175 | **−0.280** | ± 0.026, [−0.329, −0.230] | 0 / 12 | −0.340 |
| Remove gyro-bias estimation (paper Table II row) | −1.634 | **−1.047** | ± 0.119, [−1.274, −0.805] | 0 / 12 | — |
| Doppler only (DRO-D) | — | −5.244 | ± 0.264 | 0 / 12 | −4.390 |
| Dead reckoning as candidate | −165.03 (failed) | −165.21 (failed: not better than dead reckoning) | — | — | — |

The ordering is right, and every listed improvement or degradation is outside its 95 % CI except smoothing-only, which ties. Train and test agree on sign and size for every variant scored on both.

The calibration variant is a tradeoff, not a Pareto improvement:
- **Structured:** worse by −0.206 rank, on all 6 landmark-rich sequences, because shrinking lateral velocity hurts where geometry already pins it.
- **Tunnel:** better by +0.426 rank, on all 6 tunnel sequences.

The weighted rank favours it because tunnels carry more weight, as the paper's emphasis on degenerate scenes justifies (§7). The GP fix shows the enlarged test resolves even a small genuine improvement (z ≈ 2.5).

## 3. Shortcuts, before → after

| Shortcut | Before | After | Why |
|---|---:|---:|---|
| `shortcut_calibration_zero_velocity`: calibrated poses, all velocities 0 | **+0.0239** | **−165.21 failed** | Velocity–pose gap 6.405 m/s > 0.5 |
| `shortcut_calibration_constant_velocity` (new probe): calibrated poses, velocity 0 when stopped, otherwise the mean speed | — | **−165.21 failed** | Gap 1.834 m/s |
| `shortcut_generator_fit_legacy`: the redteam's 12-parameter family fit, unchanged | **+0.0593** | **−6.125** | The family no longer exists; its best fit misdescribes the motion (± 1.28; train −3.96) |
| `shortcut_generator_prior_smoother` (new probe): GP smoothing with the new generator's process covariance (correlation time from the generator), variances from train labels | — | **−0.0076** (± 0.0092, a tie) | A smooth random process leaves nothing beyond generic smoothing to exploit |
| `shortcut_unscored_heading`: heading 1e300 on scan 1 | 0 (tie) | **−165.21 failed** | Impossible heading |
| `shortcut_global_offset`: +1024 m on every position | +4e-15 (tie) | **−165.21 failed** | First pose must be the origin |
| `shortcut_global_rotation` (new probe) | — | **−165.21 failed** | First pose must have heading 0 |
| `shortcut_score_fields`: fake score/success/error fields, prewritten test report | 0 | 0 | Fields ignored, report overwritten; the candidate is the reference output (no gain) |
| `shortcut_move_baseline`: reserved-name artifacts | 0 | 0 | Ignored (listed in `ignored_artifacts`); comparator rows unchanged |
| `shortcut_comparison_compensation` | −165.03 | −165.21 failed | Frozen rows; translation eligibility |
| `shortcut_visible_answers`: copy a train label to every test sequence | −165.03 failed | −42.09 | Now eligible (22.1 % TE, 1.27 m/s velocity, both below dead reckoning) but far below the reference; pays nothing |
| `shortcut_rebuild_answers`: seed search 0–2999 by gyro fingerprint | −165.03 | −42.09 | Recovers all 6 public train seeds and no test seed; falls back to a train trajectory |
| `shortcut_fixed_artifact`: plant labels in the test inputs | −165.03 | −165.21 failed | Input digest |
| constant / truncate / timestamp / empty / null / infinite / −1e30 / duplicate name | −165.03 failed | −165.21 failed | Contract checks |

The failure rank moved from −165.03 to −165.21 only because the reference moved; the ceilings are unchanged.

**Not rerun:** the redteam's generator-fit-plus-zero-velocity combination (−0.30 before). It would now fail the same velocity-consistency rule.

## 4. Shortcuts left open, and why

- **Analysis-by-synthesis with the public renderer.** A method could fit the scene and motion of each held-out sequence by rendering `data/synthetic_radar.py` and matching the scans.
  - It is very expensive: the scene is random, with hundreds of landmarks, and the motion has no low-dimensional form.
  - It still uses the radar data, but exploits simulator knowledge that a real sensor would not give.
  - Closing it would mean hiding the sensor model, which the train split needs. `scoring/CONSTRAINTS.md` and `DIRECTION.md` forbid it; it is left to the grader.
- **Held-out inputs remain public, and the hidden test does not run methods.** The method needs no training, so in-test inference was an option. It was not adopted:
  - the reference takes about 2.5 CPU-minutes per sequence, so in-test inference would make the hidden test heavy;
  - it would also require every future method to ship an executable entry point;
  - the inputs carry no labels, and the generating seeds are hidden.
- **Tuning on visible train labels** is allowed by design: train and test are independent draws from the same generator.

## 5. Reference score before and after

**Before** (old gym, 6 held-out sequences): translation 1.355 %, rotation 0.417 deg/100 m, endpoint 1.358 m, path 1.193 %, velocity 0.115 m/s; structured 0.238 %, tunnel 2.472 %; dead reckoning 31.97 %.

**After** (`scoring/scores_test.json`, 12 held-out sequences, train-selected weight 8192):

| Group | Method | Translation (%) | Rotation (deg/100 m) | Endpoint (m) | Path length (%) | Velocity RMSE (m/s) |
|---|---|---:|---:|---:|---:|---:|
| All | dead reckoning | 31.31 | 2.047 | 15.31 | 14.09 | 3.07 (eligibility bound) |
| All | DRO-D | 4.97 | 0.347 | 4.68 | 4.75 | 0.322 |
| All | DRO-G | 1.49 | 0.297 | 1.37 | 1.31 | 0.115 |
| All | **DRO-GD (reference)** | **1.278** | **0.299** | **1.219** | **1.130** | **0.106** |
| Structured | **DRO-GD** | 0.246 | 0.306 | 0.246 | 0.087 | — |
| Tunnel | **DRO-GD** | 2.310 | 0.293 | 2.192 | 2.172 | — |

The two tests are different draws, so before and after are not directly comparable.

**Train** (6 sequences): 1.328 % / 0.336 deg/100 m / 0.118 m/s; structured 0.174 %, tunnel 2.482 %. Train and test agree within the spread across sequences.

**The paper's claim, in the paper's direction** (paired over 12 sequences, `results.json → paper_effects`):
- **DRO-GD vs dead reckoning:** better on 12/12; TE gap 30.0 ± 1.8 points.
- **DRO-GD vs Doppler-only:** better on 12/12; 3.70 ± 0.98 points, 6.89 ± 0.40 in tunnels.
- **DRO-GD vs geometry-only:** better on 12/12; 0.21 ± 0.05 points, 0.38 ± 0.04 in tunnels against 0.05 ± 0.01 in landmark-rich scenes.

As in the paper, the Doppler term matters most in the degenerate scenes, though here by a much smaller margin (§6).

`scoring/reference.json` keeps every paper-reported number unchanged. Its synthetic entries now hold the new held-out reference and comparator values; the descriptions say they are scaled replacement values, not paper numbers.

## 6. Headroom check

- **No scored metric is at its bound.** All 17 reference cells are strictly between 0 and their ceilings. The smallest are structured path length 0.087 % and structured translation 0.246 %; the largest is tunnel translation 2.31 %. A perfect method would gain +1.89.
- **Above the reference:**
  - the train-selected calibration scores +0.303, with a 95 % CI clear of zero;
  - the GP-fix pair shows the test also resolves a 0.013 improvement.
- **No single simple variant reaches the bound.** Smoothing alone and the generator-prior smoother tie the reference.
- **The baselines still make sense:** dead reckoning 31.3 % and Doppler-only 4.97 % sit far below the reference, on a scale with room above it.
- **Open directions a future agent can pursue legitimately:**
  - the tunnel-specific lateral-velocity bias (the calibration's lateral gain of 0.40), which the paper handles with a non-slip correction; the needed radar-to-axle offset is now in the manifest;
  - the Doppler-only branch at 9.2 % in tunnels, against 0.54 % in the paper;
  - the combined-objective weight, still at its grid edge;
  - gyro-bias estimation.
- **No experiment was added:** the reference is not at the bound of any metric.

## 7. Weights

Unchanged:

| Experiment | Weight |
|---|---:|
| core | 0.30 |
| tunnel | 0.25 |
| ablation (adds velocity) | 0.20 |
| structured | 0.15 |
| five paper-only experiments (never scored) | 0.10 |

Coefficients are also unchanged: translation −1, rotation −0.4, endpoint −0.25, path −0.2, velocity −0.3. Tunnel outweighs structured because the paper's Doppler constraint exists for feature-deprived scenes (§V-C).

Velocity was the cheap metric the redteam exploited. It is now protected by eligibility and consistency rather than by a larger coefficient. Raising its weight would not have stopped the zero-velocity shortcut, and it would over-weight a secondary quantity of the paper (Table II).

## 8. What I could not fix

- **The paper's Doppler advantage in tunnels is reproduced in direction, not in size.**
  - The paper: DRO-G 7.12 % against DRO-GD 0.34 % in tunnels, and DRO-D 0.54 %.
  - Here: DRO-G 2.69 % against DRO-GD 2.31 % (12/12 sequences favour GD), and DRO-D 9.2 %.
  - The infill fix helped only slightly.
  - Two reasons. The geometry-only term already sees Doppler through its per-chirp range correction; with this sensor model it constrains along-track velocity in smooth tunnels. And the Doppler-only branch keeps a speed-scale bias at grazing wall returns.
  - A skyway-like scene with moving traffic (the paper's largest gap) was not built.
- **The demonstrated large improvement is a tradeoff.** It is better in tunnels and worse in landmark-rich scenes. No Pareto-better variant larger than the GP fix was demonstrated.
- **The combined-objective weight is selected at the edge of its train grid** (8192). Its train curve has flattened.
- **Reruns were not repeated.** The method has no stochastic component, and the redteam's three earlier seed reruns matched bit for bit. This iteration did not repeat that rerun after the infill fix; the parallel execution added here does not change results.
- **The paper's real-data experiments are not scorable:** Boreas, MulRan, off-road and the automotive Tables I and II remain paper numbers in `reference.json`.

## 9. Fresh clone and maintenance

- `scripts/download.sh` restores the two tracked npz files from git, or rebuilds `data/train.npz` from `data/synthetic_radar.py`. There is no external fetch and no `shared/` reference.
- `scripts/run.sh` → `scripts/reproduce.sh` regenerates the comparators, the reference artifact and all score files, then runs `python validate.py`.
- `scripts/evaluate_test.sh` runs with no arguments and scores every `*_predictions.json` on disk.
- `bash redteam/hardening_v3/job.sh` is the maintainer pipeline: it rebuilds both splits, re-tunes on train, refreezes the comparators and replays this audit.
- The method runs sequences in parallel when CPUs allow (`DRO_WORKERS` overrides), with identical results.
