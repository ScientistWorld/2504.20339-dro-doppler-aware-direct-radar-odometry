# Reproduction Milestones

**Current: none**

<!-- Milestone levels (update "Current" above as you progress):
  none             — just started, no meaningful progress yet
  method_runs      — the paper's method executes end-to-end without errors
  core_claim       — minimum experiment supports the paper's central claim
  core_claim_plus  — core claim reproduced on additional settings
  secondary_claims — secondary results or contributions reproduced
  majority         — more than half of reported results reproduced
  near_complete    — most results reproduced, only minor gaps remain
  full             — all reported results reproduced
-->

## Progress Log

### [2026-06-04 03:52] - none
- Read the paper and identified the core DRO algorithm: direct scan-to-local-map radar intensity registration, continuous SE(2) motion correction, Doppler range correction, and optional Doppler velocity objective from up/down chirp images.
- Cloned the authors' public implementation into `method/upstream_dro/` for reference.
- Implemented a compact runnable reproduction on a synthetic spinning FMCW radar benchmark because the paper's full Doppler-enabled automotive dataset is not fully public.
- Added method, baseline, evaluation, scoring, and scripts; local syntax checks and `python validate.py` pass.

## Stop Justification
- Not stopped. A compute job is being submitted to run the method end-to-end.
