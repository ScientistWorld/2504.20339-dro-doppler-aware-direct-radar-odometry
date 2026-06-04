# Reproduction Milestones

**Current: method_runs**

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

### [2026-06-04 03:55] - method_runs
- CPU job `f0db0bd3-b7b` completed successfully and ran the synthetic data generator, baseline, DRO-D, DRO-G, DRO-GD, evaluator, and validator end-to-end.
- The resulting scores did not support the core claim: DRO-GD was worse than the fixed-velocity baseline, so the milestone remains below `core_claim`.
- Diagnosed likely Doppler alignment sign and local optimizer search issues; fixed the Doppler objective convention and added a coarse-to-local velocity search before resubmission.

### [2026-06-04 04:00] - method_runs
- CPU job `4736bccc-2e7` completed but still did not support the core claim.
- Added a Doppler velocity initializer based on per-row up/down chirp cross-correlation and weighted least-squares radial velocity fitting.

### [2026-06-04 04:10] - method_runs
- CPU job `fb9bf823-812` completed successfully and kept the environment at `method_runs`.
- DRO-D improved slightly over the fixed-velocity baseline, but DRO-GD failed because the direct local-map term overwhelmed the Doppler velocity cue.
- Fixed the discrete Doppler initializer sign, strengthened the reduced-scale synthetic Doppler displacement, and reweighted the combined objective before another CPU reproduction run.

### [2026-06-04 04:18] - method_runs
- CPU job `8e70fbca-fde` completed successfully.
- DRO-D now improves substantially over the fixed-velocity baseline, but DRO-GD remains worse than baseline, so the core claim is not yet met for the primary combined method.
- Strengthened the Doppler anchoring in the combined objective and submitted another end-to-end CPU run.

## Stop Justification
- Not stopped. A compute job is being submitted to run the method end-to-end.
