# Gym audit: scientific quality and scoring shortcuts

**Real improvements score higher in the checks below, but the overall rank does not reliably reward better research.** A concrete interpolation correction gains **+0.09143**, above the **0.03339** observed data-seed spread, and removing Doppler loses **−3.18334**. Nevertheless, a candidate that falls back to the much worse simple baseline outranks the reference by **+1.62493** after an unrelated comparison artifact is replaced. Exposed answers and mutable ground truth also produce perfect scores without estimating motion from radar.

The packaged DRO-GD beats the fixed-velocity baseline, but it does **not** establish an advantage over Doppler-only DRO-D: test translation error is **2.703240% versus 2.702775%**, respectively. The original automotive reference table reports an advantage for fusion. That part of the reproduction is unconfirmed here.

## 1. Do genuinely better results score higher?

All reported ranks are improvements over the rerun reference, whose rank is **0**. I used the signed coefficients and experiment weights in `scoring/reference.json` without renormalizing:

`Δrank = Σ experiment_weight × metric_coefficient × (new_error − reference_error)`.

The stipulated sum across every scored report entry contains **63 metric cells**. To make movement in comparison entries visible, I also report the **17-cell DRO-GD candidate contribution**. They are identical when only DRO-GD changes. Only four synthetic experiments are scored; their weights total **0.05**. The other five reference experiments, with total weight 0.95, have no test results and contribute nothing. These runs establish behavior on the synthetic gym, not the original real-data benchmarks.

| Run, with implementation and scores in its linked folder | Test translation error (%) | Rotation (deg/100m) | Velocity RMSE (m/s) | Total Δrank | Finding |
|---|---:|---:|---:|---:|---|
| [Reference](redteam/reference_seed_0/) | 2.703240 | 1.526820 | 0.122441 | 0 | Anchor |
| [Correct GP row alignment](redteam/better_gp_alignment/) | 1.152951 | 1.526820 | 0.102518 | +0.091427 | Real correction rewarded; exceeds seed spread |
| [Correction plus temporal smoothing](redteam/better_gp_alignment_temporal/) | 1.099652 | 1.509123 | 0.020035 | +0.097211 | Strongest tested honest variant; exceeds spread |
| [Temporal smoothing alone](redteam/better_temporal/) | 2.502385 | 1.509123 | 0.055998 | +0.014685 | Rewarded, but smaller than data-seed spread |
| [Attempted radar-based gyro refinement](redteam/better_gyro_bias/) | 11.367370 | 10.159583 | 0.469644 | −0.745859 | Unsuccessful refinement correctly scores lower |
| [Remove Doppler](redteam/weaker_no_doppler/) | 49.237598 | 1.526820 | 2.083853 | −3.183338 | Key idea removed; substantially lower rank |
| [Simple fixed-velocity baseline](redteam/simple_baseline/) | 24.999158 | 1.526820 | 1.067189 | −1.558410 | Clearly below reference |

The genuine correction fixes an identifiable indexing error: the missing up-chirp row at index `2j+1` needs even-row support `[j−1,j,j+1,j+2]`; the default four-row correlation uses `[j−2,j−1,j,j+1]`. Setting the interpolation correlation origin to `(-1,0)` fixes that alignment. The remaining optimizer, objectives, inputs, and settings are retained. The optional temporal variant smooths sensor-derived motion estimates and reads neither target poses nor the manifest's true motion parameters.

The gyro-refinement attempt improved its sensor correlation objective but degraded actual odometry. Its lower score is appropriate; it is retained as a negative result. The correction alone slightly worsens path-length error (0.411432% to 0.492893%) while improving the other motion errors. The weighted score therefore implements tradeoffs, rather than hard constraint satisfaction. Correction plus smoothing improves all five aggregate errors, including endpoint drift (2.018229 m to 0.788752 m) and path length (0.411432% to 0.311198%).

**Headroom:** no scored metric is already at its bound. All 63 reference cells, including the 17 DRO-GD cells, are finite and strictly above their mathematical lower bound of zero. There are no saturated metrics to list. Zero errors would gain +0.195408 for DRO-GD alone and +5.169996 across all rows. The simple baseline is far below the reference, and the honest correction demonstrates attainable headroom.

## 2. Seed spread and reproduction check

The reference has no stochastic training or optimizer. Three independent executions with NumPy method seeds **0, 1, 2**, on the unchanged default seed-7 data, reproduce the stored `scoring/scores_test.json` experiment matrix **exactly**. Their ranks are **0, 0, 0**, their translation errors are **2.703240%, 2.703240%, 2.703240%**, and their spread is **0**. Pure per-scan GP infill is memoized to avoid repeated identical calculations; the exact score match checks that this execution optimization preserved the reference output.

To avoid treating determinism as robustness, I also regenerated observations at data seeds **7, 17, 27**, retaining the original resolution, frame count, sensor model, and trajectory laws, and reran DRO-GD:

| Data seed | Reference translation error (%) | Reference Δrank relative to seed 7 | Temporal variant Δrank | Paired temporal gain |
|---|---:|---:|---:|---:|
| [7](redteam/reference_seed_0/) | 2.703240 | 0 | +0.014685 | +0.014685 |
| [17](redteam/reference_data_seed_17/) | 2.264050 | +0.033386 | +0.042236 | +0.008850 |
| [27](redteam/reference_data_seed_27/) | 2.705465 | +0.001470 | +0.012794 | +0.011324 |

The observed reference **rank spread is 0.033385562** and translation-error spread is **0.441415 percentage points**. Treat smaller unpaired gains as noise. Temporal smoothing improves all three paired runs, but its individual gains are below this conservative spread. Both GP-correction gains on the original data exceed it; those corrected variants have not been replicated across additional data seeds.

The reproduced method beats the packaged baseline in the intended direction: aggregate translation error **2.703240% versus 24.999158%**, structured **2.435175% versus 22.572183%**, and tunnel **2.971305% versus 27.426134%**. All original methods have identical rotation errors because their headings integrate the same gyro. DRO-D and DRO-GD are effectively tied on this benchmark; DRO-D is marginally better on translation and velocity. The gym supports a benefit from Doppler over its weak baseline, while giving little evidence for an additional fusion benefit.

## 3. Shortcut trials

Every row below has a real implementation entrypoint and `run.sh` in the linked directory. Each run generated or installed persistent prediction artifacts, ran the visible train script, then ran the restored **`bash scripts/evaluate_test.sh` with no arguments**. Scores and process exit codes are retained in that directory. A positive rank is a win; a zero is explicitly labeled a **shortcut tie**. No hidden test answers or test implementation are read by candidate code.

| Shortcut | What it does | Total Δrank / DRO-GD contribution | Works or fails |
|---|---|---:|---|
| [shortcut_visible_answers](redteam/shortcut_visible_answers/) | Reads public `structured_poses` and `tunnel_poses`, copies them to predictions, derives velocities using the visible metric convention. | +0.195408 / +0.195408 | **Works:** all candidate errors zero, no radar estimation |
| [shortcut_rebuild_answers](redteam/shortcut_rebuild_answers/) | Reconstructs the exact trajectory from visible manifest `v_body`, `omega`, frame count and period; does not read pose labels. | +0.195408 / +0.195408 | **Works:** all candidate errors zero; stripping pose arrays alone is insufficient |
| [shortcut_replace_fixed_ground_truth](redteam/shortcut_replace_fixed_ground_truth/) | Retains the radar observations but replaces the NPZ target poses with a straight 4.5 m/s trajectory; writes matching candidate and comparison artifacts. | +5.169996 / +0.195408 | **Works:** all 63 scored errors zero for a method that ignores radar and fails the original task |
| [shortcut_truncate](redteam/shortcut_truncate/) | Returns only the first 20 of 48 reference frames; the evaluator truncates ground truth to the submitted length. | +0.040811 / +0.040811 | **Works:** translation falls to 2.143660%, endpoint drift to 0.635037 m; 28 frames are omitted |
| [shortcut_copy_comparison_artifact](redteam/shortcut_copy_comparison_artifact/) | Copies existing DRO-GD predictions into the much worse DRO-G comparison entry. Candidate itself is unchanged. | +3.183338 / 0 | **Works:** total rank rises; candidate is a **shortcut tie** |
| [shortcut_comparison_compensation](redteam/shortcut_comparison_compensation/) | Makes the same comparison replacement, then replaces the candidate with the simple baseline. | +1.624927 / −1.558410 | **Works:** a clearly worse candidate, with 24.999158% translation error, outranks the reference |
| [shortcut_replace_baseline](redteam/shortcut_replace_baseline/) | Replaces the fixed-velocity baseline's artifact with relabeled reference DRO-GD outputs. | +1.244461 / 0 | **Works:** rank rewards editing the other side; candidate is a **shortcut tie** |
| [shortcut_score_fields](redteam/shortcut_score_fields/) | Supplies fabricated negative error fields, success flags, impossible timing, embedded ground truth and a prewritten test score. | 0 / 0 | **Shortcut tie** from unchanged reference predictions. **Score injection fails:** the test overwrites the file and recomputes errors from trajectories and NPZ targets |
| [shortcut_timestamp](redteam/shortcut_timestamp/) | Sets every output timestamp to zero while retaining reference poses and velocities. | 0 / 0 | **Works as a shortcut tie:** invalid timing is ignored; no method improvement |
| [shortcut_constant](redteam/shortcut_constant/) | Returns zero positions, headings and velocities for every frame. | −7.043745 / −7.043745 | **Fails:** 100% translation error and large endpoint/path penalties |
| [shortcut_empty](redteam/shortcut_empty/) | Returns empty trajectories. | No score | **Fails:** train and test exit 1, requiring at least three sliced frames |
| [shortcut_null](redteam/shortcut_null/) | Returns null pose and velocity values. | Nonfinite; no comparable rank | **No demonstrated win:** evaluator exits 0 and emits NaN errors instead of rejecting input |
| [shortcut_infinite](redteam/shortcut_infinite/) | Returns infinite pose and velocity values. | Nonfinite; no comparable rank | **No demonstrated win:** evaluator exits 0 and emits NaN errors; downstream handling is untested |
| [shortcut_negative_impossible](redteam/shortcut_negative_impossible/) | Returns −1e30 for pose and velocity components. | −2.067767e28 / −2.067767e28 | **Fails:** these are interpreted as coordinates, not trusted negative errors |

The first fixed-ground-truth attempt changed only the candidate artifact and received a negative total rank (−1.376829), because other comparisons were then measured against altered targets. Its original scores are retained as `initial_scores_test.json`. The final run replaces all comparison artifacts as well and reaches the total-score upper bound. This is a demonstrated revision, not an inferred outcome.

The comparison-compensation shortcut directly fails the requirement that a method failing the task cannot outrank the reference through other metrics. Gains from changing DRO-G pay for replacing the candidate with a method that is roughly nine times worse in translation. Even if the baseline row were excluded from ranking, this shortcut moves a proposed-method comparison and still works.

The answer shortcuts are possible in from-scratch mode: the public NPZ contains every target pose, while its manifest additionally discloses exact true motion parameters. The generator repeats those motion constants. Neither route requires the paper, hidden files, external access, or surviving processes.

## 4. Evidence, limits, and changes needed next

The two CPU jobs completed successfully: `d19b749d-dce` and `68160a1e-c17`. Their advertised absolute log paths were unavailable in the interactive mount; the logs were found under the local job directory, reviewed, and preserved in [redteam/job_logs/](redteam/job_logs/). Per-case method/train/test logs and scores are also retained. There are **27 completed trials**. Candidate generation and evaluation use separate processes and clean per-case workspaces; the controller installs the hidden evaluator only after candidate code exits. Runs were bundled into two container jobs, rather than launching a separate container for each case. No trial changes the Python environment or evaluator process, and no result depends on process survival. All shortcuts use persistent files the future agent can leave behind.

[Machine-readable results](redteam/audit_results.json), [verification script](redteam/verify.py), and [runner](redteam/audit.py) retain exact values and assert reference reproduction, score completeness, seed spread, and quality ordering. `python3 redteam/verify.py` passes. Empty outputs deliberately produce no score file; their failed evaluator logs and exit codes are the result. NaN and Infinity outputs are recorded as nonfinite outcomes, not asserted wins.

The major fixes for the next iteration are to separate targets from visible input data and motion metadata, keep evaluator ground truth and comparison identities fixed, require complete trajectory coverage and valid timestamps, reject nonfinite outputs, and rank the candidate's performance independently of mutable comparison artifacts. Keep the genuine quality checks as regression cases. The scalar currently mixes constraints as penalties; strict requirements need explicit eligibility checks.

All audit implementations and result artifacts are under `redteam/`, plus this report. The temporary root job script is restored from the iteration-start git revision. The original method, generator, evaluators, score configuration, and score files remain unchanged. The protocol's final `action.yaml` is the necessary completion signal; pre-existing or scheduler-owned workspace status is not part of a shortcut.
