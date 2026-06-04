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

## Stop Justification
- Not stopped; a CPU job is being submitted to regenerate scenario-specific scores for potential `core_claim_plus`.
