# Reproduction Milestones

**Current: core_claim**

## Progress Log

### [2026-06-04 04:32] - core_claim
- Implemented and packaged a compact DRO reproduction that preserves the paper's core computation: continuous SE(2) scan correction, Doppler range correction, up/down chirp infill, Doppler cross-correlation, direct local-map registration, and low-pass local-map update.
- Ran the full synthetic FMCW radar benchmark end-to-end through `scripts/reproduce.sh` in prior compute jobs.
- `dro_gd` achieved `10.90%` average relative translation error versus `25.05%` for the fixed-velocity gyro baseline on the local structured/tunnel benchmark, while preserving the heading-error constraint.
- `scripts/evaluate.sh` writes method-agnostic scores to `scoring/scores.json`, and `python validate.py --compare` passes.

## Stop Justification
- Completed at milestone `core_claim`.
- Higher milestones would require additional large public robotics datasets or the paper's full Doppler-enabled automotive dataset, which is not fully public in the paper release.
