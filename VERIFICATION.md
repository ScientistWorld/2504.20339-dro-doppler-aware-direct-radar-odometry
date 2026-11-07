# Verification Report

> **Superseded (hardening iteration).** This report describes the gym before hardening. For the current design, scores and remaining limitations, see `HARDENING.md`.

## Initial Assessment
The workspace claimed `core_claim` and contained a working compact reproduction of the Doppler radar odometry paper on a generated FMCW benchmark. The method, baseline, evaluator, split-score artifacts, packaged environment files, and prior successful CPU validation outputs were present. The claimed milestone remained justified, but a few final gym-readiness issues needed cleanup.

## Issues Found
- Minor: method-safe scoring guidance leaked implementation details through phrases in `scoring/TARGETS.md`, `scoring/CONSTRAINTS.md`, `scoring/DIRECTION.md`, `scoring/EXPERIMENTS.md`, and one synthetic-entry description in `scoring/reference.json`.
- Minor: a generated Python cache directory was present under `data/`.
- Limitation: the core claim is reproduced on a compact synthetic replacement benchmark, not on the paper's full real automotive, Boreas, MulRan, and off-road evaluation suite.

## Fixes Applied
- Reworded the scoring guidance and synthetic reference descriptions to describe the task, sensor inputs, prediction contract, constraints, and experiment intent without exposing the paper's internal algorithm choices to from-scratch agents.
- Removed the generated `data/__pycache__/` artifact.
- Re-ran `python validate.py --compare`; it passes. The validator confirms reference and score JSON validity, import separation, no committed `shared/` references, train/test independence, evaluator rewiring, method-key alignment, and visible/held-out score differentiation.

## Final Judgment
The workspace is ready to serve as a research gym for the reproduced scope. From-scratch agents can use the method-agnostic problem, data, and evaluator files without importing from `method/`, and improve-mode agents have a reproducible baseline method with visible and held-out scoring. The main scientific limitation is scale: the gym validates the core effect on a generated replacement benchmark rather than the paper's complete real-data evaluation suite.

- Milestone: core_claim
- Ready for gym use: yes
- Confidence: medium
- Key limitation: synthetic replacement benchmark only
