# Reproduction Milestones

**Current: core_claim**

## Progress Log

### [2026-06-04 04:47] - method_runs
- Existing compact DRO scaffold runs end-to-end and passes validation.
- Audit found the previous `core_claim` bookkeeping too optimistic because GP infill, velocity scoring, and gyro constraints were weak.
- Updated the implementation toward the paper's actual computation: local squared-exponential GP infill, cross-correlation kernel orientation, gyro measurement inputs, vector velocity scoring, and normalized gradient-ascent refinement.
- Submitting a CPU job to rerun the full packaged pipeline before claiming any higher milestone.

### [2026-06-04 05:06] - core_claim
- CPU audit job `cf4a04e5-70e` completed with exit code 0.
- Revised DRO-GD achieved `2.668%` average translation error versus `24.999%` for the fixed-velocity gyro baseline on the replacement FMCW radar benchmark.
- The evaluator also reports the constraint metrics: DRO-GD rotation error `1.489 deg/100m` and vector body-frame velocity RMSE `0.123 m/s`.
- Added evaluator support for per-scenario score groups and submitting another CPU job before claiming `core_claim_plus`.

### [2026-06-04 05:40] - core_claim
- CPU follow-up job `99110a51-e02` completed with exit code 0 and regenerated `scoring/scores.json` with four experiments.
- DRO-GD beats the fixed-velocity gyro baseline on the aggregate replacement benchmark and on both generated sub-scenarios: `2.385%` versus `22.572%` on `structured`, and `2.952%` versus `27.426%` on `tunnel`.
- `python validate.py` passes on the final workspace.
- Final milestone is kept at `core_claim` because the reproduction uses a compact synthetic replacement benchmark rather than the paper's full real automotive, Boreas, MulRan, and off-road evaluation suite.

### [2026-06-07 00:03] - core_claim
- Verified the later split-score audit job `c758ed34-2b1` completed with exit code 0.
- Held-out odd-frame scores still support the core claim: DRO-GD reached `2.703%` average translation error versus `24.999%` for the fixed-velocity gyro baseline.
- Tightened the standalone evaluator so `scripts/evaluate.sh` reports endpoint drift and path-length constraint metrics in the same prediction-artifact contract as the train/test evaluators.
- Submitting a CPU validation job to regenerate artifacts and rerun all validators inside the packaged container.

### [2026-06-07 00:08] - core_claim
- Final verification completed.
- `python validate.py` and `python validate.py --compare` pass after adding the missing scored endpoint/path metrics to `scores.json` and balancing the reproduced synthetic experiment weights.
- Milestone remains `core_claim` because the packaged gym validates the central claim on a compact synthetic replacement benchmark, not the paper's full real-data suite.

### [2026-06-07 00:13] - core_claim
- Tightened the standalone evaluator to load ground truth from `data/synthetic_dro.npz` instead of trusting prediction artifacts.
- Added guards against too-short trajectories producing empty segment metrics.
- Added the missing Table I `CT-LG` reference baseline and updated `TARGETS.md` to name endpoint and path-length constraint metrics.
- Submitting a CPU container validation job because the login-node Python environment lacks NumPy.

### [2026-06-07 00:18] - core_claim
- Final verification kept the milestone at `core_claim`.
- Cleaned method-safe scoring guidance so from-scratch agents receive task and evaluation constraints without implementation details.
- Removed a generated cache artifact and reran `python validate.py --compare`, which passes.
- Signaling done with the remaining limitation that the gym uses a compact synthetic replacement benchmark.

### [2026-11-07 16:40] - core_claim
- Hardening iteration: the held-out test is now six separately rendered sequences. Their labels and seeds live only in `eval/test/`, and the inputs digest is verified. Comparator rows are frozen in `eval/`, invalid output is scored at the failure ceilings, and a method must beat dead reckoning to be eligible.
- The scenes now have time-varying trajectories that start from rest, with a biased gyro. Two bugs were fixed: the renderer's rotation sign and the method's start-pose off-by-one. The paper's stationary gyro-bias heuristic was added, and the combined-objective weight is selected on train.
- Held-out reference DRO-GD: 1.36 % translation error and 0.42 deg/100 m rotation, versus 32.0 % / 2.72 for dead reckoning. DRO-GD beats DRO-G (1.49 %) and DRO-D (7.03 %) in every group. Every major shortcut now fails or has no effect. See `HARDENING.md`.

### [2026-11-08 01:40] - core_claim
- Final hardening iteration. The held-out test now has 12 sequences and train has 6. Both are regenerated with a motion model driven by smooth random processes, which closes the redteam's generator-family fit (+0.059 → −6.13).
- Reported velocities must now describe the reported poses (RMS gap ≤ 0.5 m/s) and must beat dead reckoning; this closes the calibrated-poses zero-velocity shortcut (+0.024 → failed). The first pose must be the origin, and headings and per-scan motion must be physically possible.
- Fixed the up-chirp GP infill row alignment in the reference and re-selected the combined weight on train (8192). Held-out DRO-GD: 1.28 % translation and 0.30 deg/100 m rotation, against 31.3 % for dead reckoning, 4.97 % for DRO-D and 1.49 % for DRO-G. DRO-GD is better than every comparator on 12/12 sequences.
- Variants order correctly with paired bootstrap noise: calibration +0.30 ± 0.05; no Doppler −0.28 ± 0.03; no gyro bias −1.05 ± 0.12; old infill −0.013 ± 0.005. See `HARDENING.md`.

## Stop Justification
- Completed at milestone `core_claim`.
