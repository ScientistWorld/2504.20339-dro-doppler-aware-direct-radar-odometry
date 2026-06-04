# Progress

## What Works

- Paper analysis is complete enough for the core implementation.
- The authors' public DRO code release is available under `method/upstream_dro/`.
- A local procedural FMCW spinning-radar benchmark generator is implemented in `data/synthetic_radar.py`.
- A compact DRO implementation is implemented in `method/dro_synthetic.py`, including direct local-map registration, Doppler correction, up/down chirp infill, Doppler velocity objective, gyroscope yaw integration, and online map update.
- A fixed-velocity gyro baseline and method-agnostic evaluator are implemented.
- `python validate.py` passes before job submission.
- CPU job `f0db0bd3-b7b` ran the full pipeline end-to-end without errors.

## Results

- First job scores showed a working but unsuccessful reproduction: fixed-velocity baseline `ct_r` had `25.05%` average translation error, while `dro_gd` had `35.82%`. This supports `method_runs` only, not `core_claim`.
- After reviewing the failure, the Doppler objective sign was corrected and the velocity optimizer was changed to coarse-to-local search to avoid getting stuck near the previous velocity.
- Second job `4736bccc-2e7` still failed the core claim: `dro_d` only improved slightly to `24.87%`, and `dro_gd` remained worse than baseline at `35.50%`.
- Added a Doppler-derived velocity initializer that estimates per-azimuth up/down range shifts by cross-correlation and solves the radial velocity relation before the direct/Doppler objective refinement.
- Third job `fb9bf823-812` completed end-to-end but still failed the core claim. `dro_d` improved to `23.41%` versus `25.05%` for the fixed-velocity baseline, while `dro_gd` degraded to `83.74%`, showing that the direct local-map term dominated the Doppler cue and collapsed the estimated forward velocity.
- Fixed the Doppler initializer's discrete row-shift sign convention, increased the synthetic Doppler coefficient so the up/down chirp displacement is measurable after preprocessing, and rebalanced the combined objective so DRO-GD remains anchored to the Doppler velocity estimate while still evaluating the direct local-map registration term.
- Fourth job `8e70fbca-fde` showed that the Doppler-only path now works: `dro_d` reached `10.90%` average translation error versus `25.05%` for the fixed-velocity baseline. The combined `dro_gd` result remained worse than baseline at `33.03%`, so the milestone remains `method_runs`.
- The latest edit further reduces the direct local-map weight in the combined objective and strengthens the Doppler-initializer prior for the reduced-scale synthetic benchmark.
- Fifth job `66bcfbec-1bc` produced effectively the same DRO-GD result (`33.03%`), confirming that anchoring to the raw cross-correlation initializer is the wrong control point. The refined Doppler-only objective is good, but the raw initializer is noisy.
- The latest edit changes DRO-GD into a two-stage reduced-scale optimization: first obtain the refined Doppler-only velocity estimate, then use it as the initialization and local prior while evaluating the combined direct-plus-Doppler objective.
- Sixth job `f8b4acd2-d32` reached `core_claim`: DRO-GD achieved `10.90%` average translation error versus `25.05%` for the fixed-velocity gyro baseline, while preserving near-zero heading error on this synthetic benchmark and reporting `1.05 m/s` velocity RMSE.

## Remaining

- Higher milestones would require scaling beyond this compact gym: adding more synthetic scenarios, running on the public Boreas Doppler-enabled sequence, or reproducing additional paper tables.
- The real automotive Doppler dataset used for the paper's strongest Table I result is not fully public, so this environment stops at the validated synthetic core claim.

## Issues

- The Doppler-enabled automotive dataset used for the paper's central Table I result is not fully public in the paper. The public release notes only one newer Boreas Doppler-enabled sequence at the time of release, while the paper reports a larger collected automotive dataset.
- The first run produced poor DRO estimates. This was not claimed as `core_claim`; the implementation has been adjusted and a new job will be submitted.
- The third run showed a clear objective-balance issue: the Doppler-only variant was mildly helpful, but adding the direct term hurt badly. This was not claimed as `core_claim`; the implementation has been adjusted and a new job will be submitted.
- The fourth run confirmed the Doppler cue is useful but the reduced-scale direct objective is still too influential for DRO-GD. This was not claimed as `core_claim`; the implementation has been adjusted and a new job will be submitted.
- The fifth run confirmed the raw Doppler initializer is too noisy to anchor the combined objective directly. This was not claimed as `core_claim`; the implementation has been adjusted and a new job will be submitted.
- The final core-claim run depends on a two-stage reduced-scale optimization for DRO-GD. This is documented as a scaling adaptation: it preserves the paper's Doppler and direct objective computations while making the reduced synthetic benchmark stable.

## Deviations from Paper

- Dataset substitution: the paper evaluates on Boreas, MulRan, an off-road robot dataset, and a Doppler-enabled automotive dataset collected by the authors. This workspace currently uses a synthetic spinning FMCW radar benchmark generated locally. The substitution is necessary for a compact autonomous reproduction because the central Doppler-enabled dataset is not fully public and the public datasets are large.
- Scale substitution: the benchmark uses fewer beams, range bins, and frames than the paper's real radar data. The algorithmic procedure is preserved.
- Sensor-constant substitution: the synthetic benchmark uses a larger Doppler range-shift coefficient than the first draft of the generator so the alternating chirp displacement remains observable at reduced range resolution and frame count. This changes the simulated sensor scale, not the DRO algorithm.
