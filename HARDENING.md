# Hardening report

**Bottom line.** All major shortcuts that `REDTEAM.md` listed as paying are closed. Each now either scores as failed (−165.03, the failure ceiling) or has no effect (rank 0, because the evaluator ignores what it changed). Genuinely worse methods score lower:

| Variant | Rank change |
|---|---:|
| Remove gyro-bias estimation | −1.63 |
| Previous reference version | −1.20 |
| Remove the Doppler objective | −0.18 |
| Doppler-only variant | −7.83 |
| Old constant-motion "smoothing" | −36.0 |

These gaps exceed the reference's own draw-to-draw spread (0.052). The earlier "better" variant (GP row alignment) still scores higher, but only by +0.029, which is within noise. The reproduction shows the paper's core claim in the paper's direction: DRO-GD at 1.36% translation error versus 32.0% for dead reckoning, and DRO-GD beats both of its single-objective variants on every scored group. The paper's large advantage of the Doppler objective in feature-poor scenes is reproduced only weakly (see §6).

Ranks use the redteam formula, `Σ weight × coefficient × (new − reference)` over `scoring/reference.json`, against the reference `scoring/scores_test.json` (rank 0). "Candidate" means the `dro_gd` row only; "all rows" sums every row of the reference report. Comparator rows are now frozen, so the two are identical in every case below. **Scale note:** the synthetic experiments now carry 0.90 of the weight instead of 0.05 (§7). New ranks are therefore about 18× larger in magnitude than the redteam's for the same error change.

Everything is reproducible from `redteam/hardening/` (`job.sh`, `audit.py`, `cases.py`):
- `results.json`: every rank, per-sequence errors, paired statistics and gyro-bias diagnostics;
- `cases/<case>/`: the scores, logs and summary for each case;
- `run1_tunnel_leak/` and `run2_stationarity/`: earlier rounds, kept for the record.

## 1. What changed in the gym

| Problem (REDTEAM.md or found here) | Fix |
|---|---|
| Test = odd frames of the same two trajectories as train; poses and exact motion parameters in the visible npz; generator repeats the constants | New held-out split: 6 separately rendered sequences. Inputs only in `data/test_inputs.npz` (tracked). Labels only in `eval/test/test_labels.json`. Their 62-bit seeds exist only in `eval/test/make_test_set.py`. Test names (`test_00..05`) do not reveal the scene type. The visible manifest carries no motion parameters. |
| Evaluator read ground truth from mutable `data/` | Test labels are read only from `eval/test/`. The evaluator verifies a SHA-256 digest of `data/test_inputs.npz` and fails every method if the file is modified or missing. |
| Baseline and comparison rows came from method-writable artifacts | Comparator rows `fixed_velocity_gyro`, `dro_d`, `dro_g` are frozen predictions in `eval/{train,test}/comparators/` (`scripts/freeze_comparators.py`). Artifacts using those names (or `dead_reckoning`) are ignored and listed in `_metadata.ignored_artifacts`. |
| Test rows filtered by the method-writable `scores_train.json` | Removed: the test report covers every artifact on disk plus the frozen rows. |
| Truncation; zero timestamps; null/inf/−1e30 outputs gave NaN, ties or wins; duplicate names crashed scoring | Strict contract. Every sequence must be present, with exactly one row of 6 finite numbers per scan, timestamps within 1 ms of the scan start, \|position\| ≤ 1e5 m and speed ≤ 100 m/s. One artifact per name. Any violation marks the method **failed**: every metric is set to its ceiling (100 %, 100 deg/100 m, 10 m/s, 100 m, 100 %). Valid values are capped at the same ceilings. |
| A method that fails the task could win through other rows or metrics | Explicit eligibility check: core average translation error must beat the frozen dead-reckoning row, otherwise failed. Even without that check, a method at 0.999× the dead-reckoning translation error and perfect on every other metric ranks −27.3. |
| Constant-velocity trajectories (a global constant-motion fit was a free "improvement"); rotation error identical for every method | Time-varying speed (stop of 2–2.75 s, smooth acceleration, oscillation) and yaw rate. Biased (±1–3 mrad/s), noisy gyro. The vehicle starts at rest, so the paper's stationary gyro-bias heuristic applies and rotation now separates methods (reference 0.42 vs dead reckoning 2.72 deg/100 m). |
| Renderer rotated landmarks by +θ instead of −θ (scans inconsistent with poses and gyro) | Fixed body-frame transform. |
| Synthetic tunnels leaked along-track structure: wall ends 20 m behind the start, inside the 77 m range | Scenes extend 100 m beyond both path ends; tunnel walls are dense (0.2 m) and smooth, with low curvature (`run1_tunnel_leak/`: before this fix, the no-Doppler variant beat the reference by +3.28). |
| KITTI metric used world-frame displacement divided by chord length | SE(2) relative displacement in the segment-start frame, divided by segment length (KITTI). Endpoint error is measured in the first-pose frame. Velocity RMSE is a vector norm. |
| Train/test scoring code shared a module (`eval/odometry_metrics.py`) | Removed. `eval/train/` and `eval/test/` are independent; `scripts/evaluate.sh` uses the train scorer. |

**Reference-method corrections.** All are faithful to the paper's procedure, rerun from the final code:
- **Start pose.** Scan k was registered at the pose of scan k−1, an off-by-one that broke the direct objective. It now starts at the pose estimated for the end of scan k−1 (paper §IV-D3).
- **Gyro bias.** Added the paper's stationary-vehicle bias heuristic (§IV-D2): average the first Q=5 stationary samples (speed < 5 cm/s), then low-pass update. Run 2 showed that waiting for all Q samples let the uncorrected bias rotate the map, which ended stationarity detection on 2 of 3 structured test sequences. The running mean is now applied while the samples accumulate.
- **Infill.** The GP infill is computed once per scan (a pure speed-up).
- **Combined-objective weight.** The relative weight of the direct term (paper Eq. 8 is an unweighted sum of two differently normalized objectives) is selected on the train split only (`method/tune_gd_weight.py`).

  | Weight | Train TE (%) |
  |---:|---:|
  | 0.12 | 6.09 |
  | 8 | 5.11 |
  | 32 | 3.72 |
  | 128 | 2.31 |
  | 512 | 1.65 |
  | 2048 | 1.42 |

  2048 was selected, at the grid edge.

The GP row-alignment issue the redteam found was deliberately left in the reference as a known headroom item.

## 2. Do better results score higher? (variants, before → after)

| Variant | Before (old gym) | After: test core TE % | After: rank | Paired over 6 held-out sequences |
|---|---:|---:|---:|---|
| Reference DRO-GD | 2.703 %, rank 0 | 1.355 | 0 (rerun reproduces the stored report exactly) | — |
| Previous reference version (run-2 code: bias only after Q samples, weight 512) | — | 1.968 | **−1.198** | worse on structured rotation (2.40 vs 0.30 deg/100 m) |
| GP row alignment (redteam's "better") | +0.091 | 1.330 | **+0.029** | TE −0.025 ± 0.015 (SE), 4/6 improved: within noise |
| Remove Doppler objective (DRO-G) | −3.183 | 1.493 | **−0.175** | TE +0.138 ± 0.045, 0/6 improved |
| Remove gyro-bias estimation (paper Table II ablation) | — | 1.822 | **−1.634** | rotation +2.30 ± 0.26, 0/6 improved |
| Doppler-only (DRO-D, frozen row) | — | 7.029 | −7.83 (if submitted) | 0/6 improved |
| Global constant-motion fit (old "temporal smoothing" win) | +0.015 | 25.53 | **−36.02** | 0/6 improved |
| Simple fixed-velocity baseline as candidate | −1.558 | 31.97 | **−165.03 (failed by the dead-reckoning check)** | — |
| Radar-based gyro refinement (old negative result) | −0.746 | not rerun | — | — |

Train and test agree for every variant (train core TE: reference 1.42, GP alignment 1.41, no gyro bias 1.73, no Doppler 1.60, constant fit 25.8), so an honest method scores alike on both.

## 3. Shortcuts, before → after

| Shortcut | Before (candidate / all rows) | After | Why |
|---|---:|---:|---|
| `shortcut_visible_answers` (copy visible labels; test has none, so copy a train answer) | +0.195 / +0.195 | **−165.03 failed** | No test labels outside `eval/test/`; fails the dead-reckoning check |
| `shortcut_rebuild_answers` (rerun the public generator over 6000 seed/scene pairs, match the gyro) | +0.195 / +0.195 | **−165.03 failed** | Test seeds hidden and 62-bit; 0 test matches (`cases/shortcut_rebuild_answers/rebuild_matches.json`: only the train sequences matched) |
| `shortcut_replace_fixed_ground_truth` (plant straight-line answers in both npz files and the train comparators; submit matching output) | +0.195 / **+5.170** | **−165.03 failed** | Hidden labels unaffected; test-input digest mismatch |
| `shortcut_truncate` (first 20 of 72 rows) | +0.041 / +0.041 | **−165.03 failed** | Incomplete trajectory |
| `shortcut_copy_comparison_artifact` (write `dro_gd` output as `dro_g` and `dro_d` artifacts) | 0 / **+3.183** | **0 / 0** | Reserved names ignored; comparator rows frozen |
| `shortcut_comparison_compensation` (above, plus candidate = dead reckoning) | −1.558 / **+1.625** | **−165.03 / −165.03** | Frozen comparators; dead-reckoning check |
| `shortcut_replace_baseline` (relabel reference output as the baseline) | 0 / **+1.244** | **0 / 0** | Baseline row frozen in `eval/` |
| `shortcut_score_fields` (fake score/success/ground-truth fields, prewritten `scores_test.json`, doctored `scores_train.json`) | 0 / 0 | **0 / 0** | Scores recomputed; extra fields and train file never read; candidate is the reference output |
| `shortcut_timestamp` (all timestamps 0) | 0 (tie) | **−165.03 failed** | Timestamps validated |
| `shortcut_constant` (all zeros) | −7.04 | **−165.03 failed** | Dead-reckoning check |
| `shortcut_empty` | no score (exit 1) | **−165.03 failed** | Report always written |
| `shortcut_null` / `shortcut_infinite` | NaN (exit 0) | **−165.03 failed** | Non-numeric / non-finite rejected |
| `shortcut_negative_impossible` (−1e30) | −2.07e28 | **−165.03 failed** | Impossible positions rejected; values capped |
| `shortcut_duplicate_name` (new: two `dro_gd` artifacts) | crash | **−165.03 failed** | Ambiguous submission |

The ranks of 0 mean the attack changed nothing. In those cases the candidate's predictions are the reference's own output, so no shortcut tie pays.

**Shortcuts left open:**
- **Analysis-by-synthesis with the public renderer.** A method could use `data/synthetic_radar.py` as an exact sensor model and fit trajectories to the test scans by inverse rendering. It does use the radar data, but exploits knowledge of the simulator that real sensors do not offer. Closing it would mean hiding the sensor model, which the train split needs. `scoring/CONSTRAINTS.md` names it as invalid; left for the grader.
- **Tuning against the visible train labels.** This is allowed by design, and train and test are independent draws.

## 4. Reference score before and after

- **Before:** test (odd frames) translation 2.703 %, rotation 1.527 deg/100 m, velocity 0.122 m/s (vector components), against a 24.999 % baseline.
- **After** (`scoring/scores_test.json`, 6 held-out sequences):

| Group | Translation (%) | Rotation (deg/100 m) | Endpoint (m) | Path length (%) | Velocity RMSE (m/s) |
|---|---:|---:|---:|---:|---:|
| Core | 1.355 | 0.417 | 1.358 | 1.193 | 0.115 |
| Structured | 0.238 | 0.299 | — | — | — |
| Tunnel | 2.472 | 0.535 | — | — | — |

  Dead reckoning: 31.97 % / 2.72 deg/100 m. Train (4 sequences): 1.422 / 0.301; structured 0.202, tunnel 2.641.

`python validate.py` and `python validate.py --post-design` both pass. `scoring/reference.json` keeps every paper-reported number unchanged. Its synthetic anchors are the reference's held-out values, with descriptions noting the scaled replacement setup.

## 5. Headroom and noise

- **No metric is at its bound.** Every reference error is strictly positive: smallest 0.238 % (structured translation), largest 2.47 % (tunnel translation). A perfect method would gain +2.07.
- **Concrete open directions:**
  - the Doppler-only branch has a ~10–12 % speed-scale bias in tunnels (DRO-D 12.2 % there);
  - the GP row alignment;
  - the tuned weight sits at the grid edge;
  - gyro-bias estimates are off by up to 1 mrad/s (test_05: −1.93 vs −2.89).
- **No experiment added.** None was needed for headroom.
- **Baselines:** dead reckoning (32 %) and the Doppler-only variant (7 %) sit clearly below the reference.
- **Noise:** the pipeline is deterministic (fixed seeds, no stochastic training). Across scenes, per-sequence reference translation error ranges from 0.23 to 2.89 % (SE 0.51); paired comparisons remove most of that.
  - The rank difference between the train draw and the test draw for the reference is 0.052.
  - Every effect claimed above exceeds this, except the GP-alignment variant.
  - The paper's effect, DRO-GD versus dead reckoning, is 30.6 ± 2.6 points paired.

## 6. What I could not fix

- **Doppler objective benefit in feature-poor scenes is only weakly reproduced.** The paper reports DRO-G failing in tunnels (7.12 %) and skyways (45.8 %) while DRO-GD stays under 0.4 %. Here DRO-G works in the synthetic tunnels (2.70 % vs DRO-GD 2.47 %), because its Doppler-distortion compensation already constrains velocity (the paper also notes 3 of 4 tunnel runs succeed for DRO-G). The Doppler-only variant is worse than in the paper (12.2 % in tunnels), consistent with infill and range-truncation effects of wall returns at grazing incidence in this renderer. Removing the Doppler objective costs only −0.175 rank, though consistently on 6/6 sequences. A skyway-like scene with moving traffic would probably be needed to reproduce the large gap; it was not attempted within the compute budget.
- **The redteam's "better" variant is now marginal** (+0.029, within noise), because the train-selected weight lets the direct term dominate. The clearly separated better/worse evidence is the bias-heuristic fix (+1.20), the gyro-bias ablation (−1.63) and the no-Doppler ablation (−0.175).
- **Small test set.** The test has 6 sequences (3 per scene type), so per-group values carry sampling noise. Train/test agreement is within 20 % on the core metrics.
- **Paper real-data experiments are not scorable.** Boreas, MulRan, off-road and the automotive Table I/II remain in `reference.json` as paper numbers only.

## 7. Weights

| Experiment | Old weight | New weight |
|---|---:|---:|
| `synthetic_doppler_core` | 0.02 | 0.30 |
| `synthetic_doppler_tunnel` | 0.01 | 0.25 |
| `synthetic_doppler_ablation` | 0.01 | 0.20 |
| `synthetic_doppler_structured` | 0.01 | 0.15 |
| Five paper-only experiments (never scored) | 0.95 | 0.10 total (0.03 / 0.02 / 0.02 / 0.015 / 0.015) |

- **Why the shift:** only the synthetic experiments can be scored, so with 0.05 the whole rank was confined to 5 % of the weight.
- **Tunnel above structured:** the Doppler constraint exists for feature-deprived scenes (paper §V-C).
- **Ablation at 0.20:** it carries velocity accuracy and the gyro (rotation) constraint of Table II.
- **Coefficients unchanged:** translation −1, rotation −0.4, endpoint −0.25, path length −0.2, velocity −0.3.

## 8. Fresh clone

- `scripts/download.sh` restores the two tracked npz files, or regenerates `data/train.npz` from `data/synthetic_radar.py`. There is no external fetch and no `shared/` reference.
- `scripts/run.sh` → `scripts/reproduce.sh` regenerates comparators, the reference artifact and all three score files.
- `scripts/evaluate_test.sh` runs with no arguments and scores every `*_predictions.json` on disk.
- Gym maintenance:
  - `python eval/test/make_test_set.py --force` rebuilds the hidden split;
  - `python scripts/freeze_comparators.py` refreezes the comparator rows;
  - `bash redteam/hardening/job.sh` reruns this audit.
