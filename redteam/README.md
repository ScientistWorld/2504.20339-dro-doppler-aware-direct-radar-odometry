# Radar odometry gym audit

Each case has a `method.py` implementation entrypoint and a `run.sh`. Run the
reference case first; all other cases reuse its computed prediction artifacts.
`python3 redteam/audit.py --all` bundles all cases into one CPU job.

The runner builds a clean workspace from the future agent's allowed files.
Candidate code only reads those files. After the candidate exits, the controller
restores the gym's evaluator and calls `bash scripts/evaluate_test.sh` with no
arguments in a new process. No background process or environment manipulation is
used. Independent workspaces prevent cross-case state. Test scores, train scores,
logs, predictions, and weighted comparisons are retained in each case directory.
The controller reads hidden reference scores/configuration only to report ranks,
after method generation and evaluation; candidates cannot read those files.

The reference algorithm is unchanged. Its pure GP infill function is memoized
for each unchanged scan to avoid recalculating identical images at every
candidate velocity. All optimizer steps, settings, precision, and objectives
remain unchanged. The first reference run will be compared with the original
stored test metrics. Method seeds 0, 1, 2 share fixed inputs; additional data seeds
17 and 27 measure changes in synthetic observations (the motion laws remain
constant). No packages are installed by the audit.

A positive rank is improvement over the rerun reference, using the signed
coefficients and unnormalized experiment weights from `scoring/reference.json`.
`candidate_rank` compares DRO-GD alone; `all_rows_rank` sums all report method
rows. Both are reported explicitly to distinguish candidate quality from moving
an unrelated comparison. The reference value is zero.

The completed audit contains 27 cases across two CPU jobs. The five follow-up
runs are bundled by `redteam/followup.sh`. See `REDTEAM.md` for the conclusions,
`redteam/audit_results.json` for exact results, and `redteam/job_logs/` for the
scheduler logs. `python3 redteam/verify.py` checks the saved evidence without
running inference.
