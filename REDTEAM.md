# Audit: does this gym reward better research?

The tested genuine improvements score higher, and the weaker variants score lower. However, the rank still rewards shortcuts: fitting the public generator's motion family beats the reference by **+0.05932043**, and reporting **zero velocity on every scan** beats it by **+0.02385841**. The latter fails a stated output objective while pose gains pay for the velocity penalty. The observed reference seed spread is **0**.

This report supersedes the earlier audit in this file. Only the new runs linked below are evidence for this iteration. Positive rank means improvement over the reference, whose rank is zero.

| Genuine variant; folder contains its method, `run.sh`, predictions and test scores | Translation (%) | Rotation (deg/100 m) | Endpoint (m) | Path error (%) | Velocity RMSE (m/s) | Test rank |
|---|---:|---:|---:|---:|---:|---:|
| [Reference, seed 0](redteam/audit_ref_seed_0/) | 1.355369 | 0.417049 | 1.357740 | 1.193310 | 0.115021 | 0 |
| [Correct GP interpolation alignment](redteam/audit_better_gp/) | 1.330352 | 0.448336 | 1.327910 | 1.162750 | 0.113423 | **+0.02880308** |
| [Train-selected calibration and smoothing](redteam/audit_better_calibration/) | 1.211879 | 0.426981 | 1.091602 | 1.091266 | 0.082690 | **+0.38404031** |
| [Remove Doppler, retain geometry](redteam/audit_weaker_no_doppler/) | 1.493230 | 0.438422 | 1.438408 | 1.278574 | 0.121597 | **−0.17506895** |
| [Disable gyro bias estimation](redteam/audit_weaker_no_gyro_bias/) | 1.821546 | 2.717569 | 3.106859 | 1.340438 | 0.118573 | **−1.63419167** |
| [Simple 4.5 m/s, raw-gyro baseline](redteam/audit_simple_baseline/) | 100* | 100* | 100* | 100* | 10* | **−165.03489184** |

All columns except rank are aggregate errors; lower is better. *The simple baseline fails the strict requirement to beat that same fixed comparator, so the evaluator assigns every ceiling. Its actual translation error in the frozen comparator row is **31.971912%**. The low rank is an eligibility penalty, not its raw error.

The GP variant corrects the half-grid alignment of even-row interpolation by setting the correlation origin to `(-1, 0)` on even-infill calls. It retains the reference objectives, optimizer, map, settings and data. Its translation, endpoint, path and velocity errors improve, while rotation worsens slightly. Calibration fits two global velocity gains from labelled training velocities and selects a smoothing window using training pose error. Test inference uses sensor estimates and gyro samples. The chosen gains are `[1.01393446, 0.55372418]`, with a nine-scan quadratic Savitzky–Golay filter. Both improvements and both degradations exceed the measured seed spread.

Neither improvement is a Pareto improvement. Calibration worsens structured-scene translation from **0.238310% to 1.334278%** and path error from **0.096516% to 1.246596%**, while improving tunnel translation from **2.472428% to 1.089479%**. The weighted rank allows these tradeoffs. These checks establish sensitivity to real method changes, not that every higher rank is scientifically preferable.

The reference is beatable. **No scored reference metric is at its bound:** all **17 candidate metric cells**, and all **63 cells including frozen comparators**, lie strictly between zero and their failure ceilings. There are no saturated cells to list. Perfect candidate errors would gain **+2.06510816**, with comparators fixed; the two honest variants demonstrate attainable headroom.

The reference was rerun independently with method seeds **0, 1 and 2**, without reusing another rerun's predictions or memoizing scan computations:

| Seed | Saved run | Translation error (%) | Test rank |
|---|---|---:|---:|
| 0 | [audit_ref_seed_0](redteam/audit_ref_seed_0/) | 1.355368947548978 | 0 |
| 1 | [audit_ref_seed_1](redteam/audit_ref_seed_1/) | 1.355368947548978 | 0 |
| 2 | [audit_ref_seed_2](redteam/audit_ref_seed_2/) | 1.355368947548978 | 0 |

All 17 candidate test metrics match the stored reference exactly on every rerun. The **maximum minus minimum test-rank spread is 0**, and each metric's spread is zero. This method has deterministic optimization and no stochastic training. These are method-seed repetitions on fixed test inputs, not independent test datasets; they do not measure sampling uncertainty or generalization. The approximately `4e-15` offset result below is floating-point roundoff and is classified as a numerical tie.

The reproduced fusion method beats its baseline in the reported translation direction on this synthetic benchmark. The independent rerun matches the frozen reference, including the geometry-only ablation:

| Method | Aggregate translation (%) | Structured (%) | Tunnel (%) | Rotation (deg/100 m) | Velocity RMSE (m/s) |
|---|---:|---:|---:|---:|---:|
| Fixed-velocity/raw-gyro baseline | 31.971912 | 26.094728 | 37.849095 | 2.717569 | Not scored |
| DRO-D, Doppler only | 7.028721 | 1.860779 | 12.196663 | 0.356442 | 0.454346 |
| DRO-G, geometry only | 1.493230 | 0.286815 | 2.699644 | 0.438422 | 0.121597 |
| DRO-GD, reproduced fusion | **1.355369** | **0.238310** | **2.472428** | 0.417049 | **0.115021** |

Fusion improves translation and velocity over both ablations, but does not beat Doppler-only rotation. The real-data paper results are not reproduced by these tests. The gym explicitly substitutes procedural data because the central Doppler dataset is unavailable. No paper contents were used to construct the audit candidates.

The rank uses the signed coefficients and experiment weights from `scoring/reference.json`, without renormalizing:

`rank = Σ experiment_weight × metric_coefficient × (candidate_error − reference_error)`.

Active experiments are core (weight **0.30**), structured (**0.15**), tunnel (**0.25**) and ablation (**0.20**). Coefficients are translation **−1**, rotation **−0.4**, endpoint **−0.25**, path **−0.2**, and velocity **−0.3** (ablation only). The other five configured real-data experiments, total weight **0.10**, have no hidden-test report entries and contribute nothing. Summing all 63 scored cells gives exactly the same change as summing the 17 candidate cells in every trial: comparator rows remain fixed.

Translation eligibility prevents a candidate at or below the simple baseline from compensating through other metrics: it gets every failure ceiling, rank **−165.03489184**. The simple baseline and comparison-compensation shortcut demonstrate this. Other objectives lack this protection. With calibrated poses and all velocities zero, velocity RMSE rises from **0.115021 to 6.085722 m/s**, yet the actual rank remains **+0.02385841**, with no failed-method flag. The pose gain minus velocity penalty is `0.38404031 − 0.20 × 0.30 × (6.08572163 − 0.08268996)`. Thus a method failing the velocity objective can outrank the reference. As an arithmetic headroom check, perfect poses and even the maximum velocity penalty would still score **+1.46510816**; that last number is a calculation, not a separately run candidate.

Every shortcut below was actually run through the restored hidden test. Each linked folder contains its entrypoint, `run.sh`, predictions, `scores_test.json` and `summary.json`. A tie counts as paying, as requested, and is labelled a **shortcut tie**. The reference rank is **0** throughout; **−165.03489184** denotes all failure ceilings, not a missing score.

| Shortcut | What it does | Test rank versus reference 0 | Works or fails |
|---|---|---:|---|
| [shortcut_generator_fit_v2](redteam/shortcut_generator_fit_v2/) | Fits the public generator's exact ramp, sinusoidal speed, curvature, slip and lever-arm family to gyro samples and radar velocity estimates; reintegrates that family. | **+0.05932043** | **Works.** Exploits the answer family; translation 1.324387%, velocity 0.084510 m/s. |
| [shortcut_calibration_zero_velocity_v2](redteam/shortcut_calibration_zero_velocity_v2/) | Retains calibrated moving poses, replaces every velocity with zero. | **+0.02385841** | **Works.** Velocity objective fails, RMSE 6.085722 m/s; pose gains compensate. |
| [shortcut_unscored_heading_v2](redteam/shortcut_unscored_heading_v2/) | Sets scan 1 heading to the finite but impossible value `1e300`. | **0** | **Works: shortcut tie.** All 17 errors unchanged; this stationary odd scan is absent from scored segment starts/ends. |
| [shortcut_global_offset_v2](redteam/shortcut_global_offset_v2/) | Adds 1,024 m to both position coordinates throughout, violating the required origin. | **+4.06e-15 ≈ 0** | **Works: shortcut numerical tie.** Translation-invariant metrics cannot distinguish it. |
| [shortcut_score_fields_v2](redteam/shortcut_score_fields_v2/) | Keeps reference trajectories; writes fake scores, success flags and negative runtime/error fields, including a prewritten test report. | **0** | **Shortcut tie** from unchanged predictions. Forged scoring **fails**: fields are ignored and the report overwritten. |
| [shortcut_move_baseline_v2](redteam/shortcut_move_baseline_v2/) | Keeps reference candidate; replaces reserved comparison artifacts and edits visible train comparators. | **0** | **Shortcut tie** from unchanged candidate. Moving the comparison **fails**: the restored evaluator owns comparator scores. |
| [shortcut_score_fields_bad_v2](redteam/shortcut_score_fields_bad_v2/) | Uses zero poses plus fabricated success/error fields. | **−165.03489184** | **Fails.** Recomputed translation eligibility overrides the fields. |
| [shortcut_comparison_compensation_v2](redteam/shortcut_comparison_compensation_v2/) | Replaces comparators and uses the weak simple-baseline candidate. | **−165.03489184** | **Fails.** Frozen comparisons cannot pay for the failing candidate. |
| [shortcut_visible_answers_v2](redteam/shortcut_visible_answers_v2/) | Uses visible train labels and copies a training trajectory to held-out names. | **−165.03489184** | **Fails.** Visible labels do not contain test answers. |
| [shortcut_rebuild_answers_v2](redteam/shortcut_rebuild_answers_v2/) | Searches public generator seeds 0–2,999 in both scene classes by gyro fingerprint; falls back to a training trajectory. | **−165.03489184** | **Fails on test.** Recovers all four training seeds/scenes, but no held-out sequence. Larger searches remain untested. |
| [shortcut_generator_zero_velocity_v2](redteam/shortcut_generator_zero_velocity_v2/) | Uses generator-fit poses but reports zero velocities. | **−0.30075227** | **Fails.** Its smaller pose gain cannot pay for velocity RMSE 6.085722 m/s. |
| [shortcut_fixed_artifact_v2](redteam/shortcut_fixed_artifact_v2/) | Replaces public input archives with fake constant-pose labels and matching predictions. | **−165.03489184** | **Fails.** Test-input digest detects replacement. Train exits 1 on degenerate labels; restored test exits 0 with a failure score. |
| [shortcut_constant_v2](redteam/shortcut_constant_v2/) | Reports zero poses and velocities throughout. | **−165.03489184** | **Fails.** Translation eligibility. |
| [shortcut_empty_v2](redteam/shortcut_empty_v2/) | Reports empty trajectories. | **−165.03489184** | **Fails.** Zero rows instead of 72. |
| [shortcut_null_v2](redteam/shortcut_null_v2/) | Reports null pose/velocity fields. | **−165.03489184** | **Fails.** Rows must contain numbers. |
| [shortcut_infinite_v2](redteam/shortcut_infinite_v2/) | Reports infinite forward velocity. | **−165.03489184** | **Fails.** Nonfinite validation. |
| [shortcut_impossible_v2](redteam/shortcut_impossible_v2/) | Reports `−1e30` pose and velocity components. | **−165.03489184** | **Fails.** Impossible-position validation. |
| [shortcut_duplicate_v2](redteam/shortcut_duplicate_v2/) | Leaves two artifacts claiming the same candidate name. | **−165.03489184** | **Fails.** Duplicate-name validation. |

The generator-fit shortcut recovers neither exact labels nor a hidden seed. It uses shipped `data/synthetic_radar.py` equations, fits 12 motion parameters with six deterministic initializations using sensor residuals, and integrates on the public beam-time grid. No test score selects its fit. It gains rank without improving the radar estimator and is explicitly excluded by the visible constraints against recovering trajectories from the generator. Six held-out sequences from the same family remain vulnerable after labels are separated and seeds changed.

The shortcut ties involving forged fields and changed comparators do not demonstrate trust in those edits. They pay because valid reference predictions remain. The impossible-heading and origin-offset shortcut ties expose actual output-contract gaps. There is no fixed pretrained model to retrain; the fixed input artifact and reserved comparator artifacts were tested instead. No environment, evaluator-process or background-process interference was attempted.

The next iteration should make velocity consistency and required origin/heading behavior eligibility conditions, validate angular changes at every scan, and add motion families that cannot be reconstructed from the shipped simulator. Keep label separation, the input digest, frozen comparators and malformed-output checks. Retain the genuine quality variants as regression cases.

The [controller](redteam/audit_v2/controller.py) creates a separate workspace per case under `redteam/`, copying only future-agent-visible files. Candidate code has no paper, hidden labels/evaluator, score reference, prior audit outputs or git history. These runs audit **improve mode**; several depend on the supplied implementation, and no from-scratch success is claimed. Cheap output-only checks reuse reference predictions computed from visible sensor inputs in this audit. After the candidate exits, the controller restores the complete `eval/` tree and test script, retains other candidate edits, and runs **`bash scripts/evaluate_test.sh` with no arguments** as a new process. Tests were bundled in two fresh scheduled containers; no candidate changes the Python environment or leaves a surviving process, so no shortcut depends on sharing a container between these subprocesses.

There are **26 completed cases**, each with a successful hidden-test invocation, across CPU jobs `d9fdac9d-87c` and `be8180eb-23e`. The second job corrects bounded seed recovery and adds the decisive calibrated-zero-velocity shortcut. Final evidence is in [results.json](redteam/audit_v2/results.json), [job receipts](redteam/audit_v2/job_receipts.json), and each saved test score. `bash redteam/<case>/run.sh --force` reruns a case in the gym container; omit `--force` to reuse its result. The [verification script](redteam/audit_v2/verify.py) checks all saved scores, 63-cell ranks, comparator immutability, seed spread and shortcut artifacts without rerunning inference.

The method, data, evaluator, briefing, score configuration and score reports are unchanged. Temporary `scripts/run.sh` is restored with git from the iteration-start revision. Audit-owned changes are confined to `redteam/` and this report; `action.yaml` is the required completion signal. Scheduler job files are reduced to receipts under `redteam/`. Pre-existing managed README/manifest and trajectory status is recorded in [start_state.json](redteam/audit_v2/start_state.json) and is not an audit edit. The existing reproduction milestone remains `core_claim`; this audit establishes no new paper-reproduction milestone.
