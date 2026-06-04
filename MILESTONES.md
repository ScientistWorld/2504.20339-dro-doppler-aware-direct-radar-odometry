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

## Stop Justification
- Finalized at `core_claim`. The paper's actual DRO computation is implemented and validated on a non-trivial synthetic FMCW radar benchmark with aggregate, per-scenario, and ablation/constraint metrics. Higher milestones are not claimed because the central Doppler-enabled automotive dataset is not fully public and the remaining public real-data tables would require substantially larger dataset setup beyond this compact gym.
