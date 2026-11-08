"""Hardening audit, final iteration.

Every case builds ONE candidate artifact (method name ``dro_gd``) from files a
future agent can see (inputs, visible train labels, the reference and
comparator outputs, the public generator). The candidate is copied into a
fresh mini workspace that holds only what the hidden test needs
(``eval/test/``, ``scripts/evaluate_test.sh``, ``data/test_inputs.npz`` and
the candidate under ``checkpoints/``), then ``bash scripts/evaluate_test.sh``
runs there with no arguments. The report is ranked against the reference
report ``scoring/scores_test.json`` with the experiment weights and signed
metric coefficients of ``scoring/reference.json``:

    rank = sum_exp weight * sum_metric coefficient * (candidate - reference)

Honest variants are also scored on the visible train split, and every scored
variant gets a paired, scene-stratified bootstrap of its rank difference over
the held-out sequences (both methods see the same resampled sequences).

Usage:
    python redteam/hardening_v3/audit.py                  # all cases (resumes)
    python redteam/hardening_v3/audit.py --skip-expensive # skip method reruns
    python redteam/hardening_v3/audit.py --force a,b      # recompute cases
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares
from scipy.signal import savgol_filter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CASES_DIR = HERE / "cases"
WS_ROOT = ROOT / "tmp" / "hardening_v3_ws"
CACHE = ROOT / "checkpoints" / "cache_audit"
TRAIN = ROOT / "data" / "train.npz"
TEST = ROOT / "data" / "test_inputs.npz"
REF_PRED = ROOT / "checkpoints" / "dro_synthetic" / "dro_gd_predictions.json"
COMPARATORS = ROOT / "checkpoints" / "comparators"
BOOTSTRAP = 4000

EXP_GROUPS = {
    "synthetic_doppler_core": None,
    "synthetic_doppler_structured": "structured",
    "synthetic_doppler_tunnel": "tunnel",
    "synthetic_doppler_ablation": None,
}
PER_SEQ_KEY = {
    "avg_translation_error_pct": "translation_error_pct",
    "avg_rotation_error_deg_per_100m": "rotation_error_deg_per_100m",
    "translation_error_pct": "translation_error_pct",
    "rotation_error_deg_per_100m": "rotation_error_deg_per_100m",
    "endpoint_position_error_m": "endpoint_position_error_m",
    "path_length_error_pct": "path_length_error_pct",
    "velocity_rmse_mps": "velocity_rmse_mps",
}


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # lets forked workers unpickle module functions
    spec.loader.exec_module(module)
    return module


dro = load_module(ROOT / "method" / "dro_synthetic.py", "dro_audit")
gen = load_module(ROOT / "data" / "synthetic_radar.py", "gen_audit")
hidden = load_module(ROOT / "eval" / "test" / "evaluate.py", "hidden_eval_audit")


# ----------------------------------------------------------------- inputs

def load_inputs() -> dict:
    seqs = {}
    for path, labelled in ((TRAIN, True), (TEST, False)):
        with np.load(path, allow_pickle=False) as data:
            manifest = json.loads(str(data["manifest_json"].item()))
            period = float(manifest["sensor"]["frame_period"])
            for name in sorted(manifest["sequences"]):
                seq = {
                    "frame_times": np.asarray(data[f"{name}_frame_times"], dtype=np.float64),
                    "gyro_yaw": np.asarray(data[f"{name}_gyro_yaw"], dtype=np.float64),
                    "period": period,
                    "split": "train" if labelled else "test",
                }
                if labelled:
                    seq["poses"] = np.asarray(data[f"{name}_poses"], dtype=np.float64)
                    seq["velocities"] = np.asarray(data[f"{name}_velocities"], dtype=np.float64)
                    seq["scenario"] = manifest["sequences"][name]["scenario"]
                seqs[name] = seq
    return seqs


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def renamed(artifact: dict, sequences: dict | None = None) -> dict:
    return {"method": "dro_gd", "sequences": sequences if sequences is not None else artifact["sequences"]}


def traj(artifact: dict, name: str) -> np.ndarray:
    return np.asarray(artifact["sequences"][name]["trajectory"], dtype=np.float64)


# ------------------------------------------------------- post-processing

def integrate(times: np.ndarray, velocity: np.ndarray, gyro: np.ndarray, bias: float) -> list:
    """Constant body velocity and gyro yaw rate per scan, exact arc integration."""
    xy = np.zeros(2)
    theta = 0.0
    rows = []
    for k, t in enumerate(times):
        rows.append([float(t), float(xy[0]), float(xy[1]), float(theta), float(velocity[k, 0]), float(velocity[k, 1])])
        if k + 1 < len(times):
            dt = float(times[k + 1] - t)
            w = float(gyro[k] - bias)
            if abs(w) < 1e-10:
                body = velocity[k] * dt
            else:
                a = w * dt
                s, c = math.sin(a), math.cos(a)
                body = np.array([s * velocity[k, 0] - (1 - c) * velocity[k, 1], (1 - c) * velocity[k, 0] + s * velocity[k, 1]]) / w
            c, s = math.cos(theta), math.sin(theta)
            xy = xy + np.array([[c, -s], [s, c]]) @ body
            theta += w * dt
    return rows


def stationary_bias(old: np.ndarray, gyro: np.ndarray) -> float:
    stationary = np.linalg.norm(old[:, 4:6], axis=1) < 0.05
    return float(np.mean(gyro[stationary])) if np.any(stationary) else 0.0


def reintegrate(ref: dict, seqs: dict, velocity_fn) -> dict:
    out = {}
    for name, seq in seqs.items():
        old = traj(ref, name)
        vel = velocity_fn(name, old)
        out[name] = {"trajectory": integrate(seq["frame_times"], vel, seq["gyro_yaw"], stationary_bias(old, seq["gyro_yaw"]))}
    return out


def train_position_error(sequences: dict, seqs: dict) -> float:
    errs = []
    for name, seq in seqs.items():
        if seq["split"] != "train":
            continue
        rows = np.asarray(sequences[name]["trajectory"])
        errs.append(float(np.mean(np.linalg.norm(rows[:, 1:3] - seq["poses"][:, 1:3], axis=1))))
    return float(np.mean(errs))


def calibrate(ref: dict, seqs: dict, allow_gain: bool) -> tuple[dict, dict]:
    """Global velocity gains fitted on train labels + Savitzky-Golay smoothing,
    window (and whether to use the gains) chosen by train position error."""
    train = {n: s for n, s in seqs.items() if s["split"] == "train"}
    feats = np.concatenate([traj(ref, n)[:, 4:6] for n in train])
    targets = np.concatenate([train[n]["velocities"] for n in train])
    gains = (feats * targets).sum(axis=0) / np.maximum((feats**2).sum(axis=0), 1e-12)
    best = None
    for use_gain in ((False, True) if allow_gain else (False,)):
        gain = gains if use_gain else np.ones(2)
        for window in (1, 5, 9, 13):
            def vel(name, old, gain=gain, window=window):
                v = old[:, 4:6] * gain
                return savgol_filter(v, window, 2, axis=0) if window > 1 else v
            err = train_position_error(reintegrate(ref, train, vel), train)
            if best is None or err < best[0]:
                best = (err, gain, window, vel)
    err, gain, window, vel = best
    return reintegrate(ref, seqs, vel), {"train_position_error_m": err, "gain": [float(g) for g in gain], "window": int(window)}


def gp_prior_smoother(ref: dict, seqs: dict) -> tuple[dict, dict]:
    """GP smoothing of per-scan velocity estimates with the public generator's
    squared-exponential process covariance (correlation time = midpoint of
    the generator's range); signal/noise variances from visible train labels."""
    train = [n for n, s in seqs.items() if s["split"] == "train"]
    est = np.concatenate([traj(ref, n)[:, 4:6] for n in train])
    lab = np.concatenate([seqs[n]["velocities"] for n in train])
    noise_var = np.mean((est - lab) ** 2, axis=0)
    signal_var = np.var(lab, axis=0)
    tau = 0.5 * (0.8 + 1.6)
    out_vel = {}
    for name, seq in seqs.items():
        t = seq["frame_times"] + 0.5 * seq["period"]
        d2 = (t[:, None] - t[None, :]) ** 2
        old = traj(ref, name)
        smooth = np.zeros_like(old[:, 4:6])
        for axis in range(2):
            mean = float(np.mean(old[:, 4 + axis]))
            k = 0.5 * signal_var[axis] * np.exp(-d2 / (4.0 * tau**2)) + signal_var[axis] * np.exp(-d2 / (2.0 * 3.0**2))
            y = old[:, 4 + axis] - mean
            smooth[:, axis] = mean + k @ np.linalg.solve(k + noise_var[axis] * np.eye(len(t)), y)
        out_vel[name] = smooth
    return reintegrate(ref, seqs, lambda name, old: out_vel[name]), {
        "tau_s": tau, "noise_var": noise_var.tolist(), "signal_var": signal_var.tolist(),
    }


def legacy_body_motion(p: dict, t: np.ndarray):
    """Motion family of the PREVIOUS public generator (ramp x sinusoid speed,
    sinusoid curvature, constant slip), as exploited by the redteam."""
    ramp = gen.smoothstep((t - p["t_stop"]) / p["t_acc"])
    osc = p["speed_amp"] * np.sin(2.0 * np.pi * (t - p["t_stop"]) / p["speed_period"] + p["speed_phase"])
    speed = ramp * (p["v_cruise"] + osc)
    kappa = p["kappa0"] + p["kappa1"] * np.sin(2.0 * np.pi * t / p["kappa_period"] + p["kappa_phase"])
    omega = speed * kappa
    return speed, gen.RADAR_LEVER_ARM_M * omega + p["slip"] * ramp, omega


def legacy_generator_fit(ref: dict, seqs: dict) -> tuple[dict, dict]:
    """The redteam's +0.059 shortcut, unchanged: fit the old 12-parameter
    family to the gyro samples and per-scan radar velocity estimates, then
    reintegrate the fitted family on the beam-time grid."""
    keys = ["t_stop", "t_acc", "v_cruise", "speed_amp", "speed_period", "speed_phase",
            "kappa0", "kappa1", "kappa_period", "kappa_phase", "slip", "gyro_bias"]
    low = [2.0, 4.0, 5.0, 0.3, 5.0, -2 * np.pi, -0.02, 0.0, 6.0, -2 * np.pi, -0.04, -0.005]
    high = [2.75, 6.0, 9.5, 1.5, 9.0, 4 * np.pi, 0.02, 0.018, 12.0, 4 * np.pi, 0.04, 0.005]
    out = {}
    diag = {}
    for name, seq in seqs.items():
        old = traj(ref, name)
        frames = len(old)
        t = (seq["frame_times"][:, None] + np.arange(12)[None, :] * seq["period"] / 12).ravel()
        obs_v = old[:, 4:6]
        obs_g = seq["gyro_yaw"]

        def residual(p):
            vx, vy, om = legacy_body_motion(dict(zip(keys, p)), t)
            pv = np.stack([vx, vy], axis=1).reshape(frames, 12, 2).mean(axis=1)
            pg = om.reshape(frames, 12).mean(axis=1) + p[-1]
            return np.r_[((pv - obs_v) / np.array([0.15, 0.08])).ravel(), (pg - obs_g) / 0.001]

        best = None
        for period in (5.5, 7.0, 8.5):
            for phase in (0.0, np.pi):
                p0 = [2.4, 5.0, np.clip(np.median(obs_v[-24:, 0]), 5.1, 9.4), 0.8, period, phase,
                      0.0, 0.006, 9.0, phase, 0.0, np.clip(np.mean(obs_g[:7]), -0.0049, 0.0049)]
                fit = least_squares(residual, p0, bounds=(low, high), max_nfev=250, ftol=1e-9, xtol=1e-9, gtol=1e-9)
                if best is None or np.sum(fit.fun**2) < np.sum(best.fun**2):
                    best = fit
        p = dict(zip(keys, best.x))
        tt = np.arange(frames * gen.BEAMS + 1) * gen.FRAME_PERIOD / gen.BEAMS
        vx, vy, w = legacy_body_motion(p, tt)
        dt = gen.FRAME_PERIOD / gen.BEAMS
        theta = gen._cumtrapz(w, dt)
        x = gen._cumtrapz(np.cos(theta) * vx - np.sin(theta) * vy, dt)
        y = gen._cumtrapz(np.sin(theta) * vx + np.cos(theta) * vy, dt)
        ix = np.arange(frames) * gen.BEAMS
        win = ix[:, None] + np.arange(gen.BEAMS)[None, :]
        rows = np.column_stack([seq["frame_times"], x[ix], y[ix], theta[ix], vx[win].mean(axis=1), vy[win].mean(axis=1)])
        out[name] = {"trajectory": rows.tolist()}
        diag[name] = {"residual_norm": float(np.linalg.norm(best.fun))}
    return out, diag


def legacy_infill(scan: np.ndarray):
    """infill_up_down as it was before this iteration's alignment fix."""
    raw = scan.astype(np.float32)
    even = raw[0::2] - float(np.mean(raw[0::2]))
    odd = raw[1::2] - float(np.mean(raw[1::2]))
    even_smooth = dro.correlate(even, dro.GP_SMOOTH_WEIGHTS, mode="constant", cval=0.0)
    even_interp = dro.correlate(even, dro.GP_INTERP_WEIGHTS, mode="constant", cval=0.0)
    odd_smooth = dro.correlate(odd, dro.GP_SMOOTH_WEIGHTS, mode="constant", cval=0.0)
    odd_interp = dro.correlate(odd, dro.GP_INTERP_WEIGHTS, mode="constant", cval=0.0)
    up = np.zeros_like(raw)
    down = np.zeros_like(raw)
    up[0::2] = even_smooth[: up[0::2].shape[0]]
    up[1::2] = even_interp[: up[1::2].shape[0]]
    down[1::2] = odd_smooth[: down[1::2].shape[0]]
    down[0::2] = odd_interp[: down[0::2].shape[0]]
    up = dro.postprocess_gp_image(up)
    down = dro.postprocess_gp_image(down)
    for img in (up, down):
        img[:4] = 0
        img[-4:] = 0
        img[:, :4] = 0
        img[:, -4:] = 0
    return up, down


def rerun_method(cfg_changes: dict, tag: str, patch_infill: bool = False) -> dict:
    cfg = dict(dro.load_config(), **cfg_changes)
    cfg["audit_variant"] = tag  # separate cache entries; ignored by the method
    original = dro.infill_up_down
    if patch_infill:
        dro.infill_up_down = legacy_infill
    try:
        results = dro.run_all([str(TEST)], "dro_gd", cfg, CACHE)
    finally:
        dro.infill_up_down = original
    return {"method": "dro_gd", "sequences": results}


# ----------------------------------------------------------------- cases

def build_case(case: str, ctx: dict) -> tuple[dict | None, dict]:
    """Returns (artifact or None, extras). extras may hold: files (relative
    path -> text), inputs_override (bytes path), info, nan_ok."""
    ref = ctx["ref"]
    seqs = ctx["seqs"]
    test_names = [n for n, s in seqs.items() if s["split"] == "test"]
    extras: dict = {}

    if case == "reference":
        return renamed(ref), extras
    if case == "weaker_no_doppler":
        return renamed(read_json(COMPARATORS / "dro_g_comparator.json")), extras
    if case == "weaker_doppler_only":
        return renamed(read_json(COMPARATORS / "dro_d_comparator.json")), extras
    if case == "simple_baseline":
        return renamed(read_json(COMPARATORS / "fixed_velocity_gyro_comparator.json")), extras
    if case == "better_calibration":
        sequences, info = calibrate(ref, seqs, allow_gain=True)
        extras["info"] = info
        return renamed(ref, sequences), extras
    if case == "better_smoothing":
        sequences, info = calibrate(ref, seqs, allow_gain=False)
        extras["info"] = info
        return renamed(ref, sequences), extras
    if case == "weaker_no_gyro_bias":
        return rerun_method({"gyro_bias_estimation": False}, "no_gyro_bias"), extras
    if case == "weaker_legacy_gp_infill":
        return rerun_method({}, "legacy_gp_infill", patch_infill=True), extras

    if case == "shortcut_generator_fit_legacy":
        sequences, info = legacy_generator_fit(ref, seqs)
        extras["info"] = info
        return renamed(ref, sequences), extras
    if case == "shortcut_generator_prior_smoother":
        sequences, info = gp_prior_smoother(ref, seqs)
        extras["info"] = info
        return renamed(ref, sequences), extras
    if case in ("shortcut_calibration_zero_velocity", "shortcut_calibration_constant_velocity"):
        sequences, info = calibrate(ref, seqs, allow_gain=True)
        for entry in sequences.values():
            rows = np.asarray(entry["trajectory"])
            if case.endswith("zero_velocity"):
                rows[:, 4:6] = 0.0
            else:
                moving = np.linalg.norm(rows[:, 4:6], axis=1) > 0.5
                rows[:, 4:6] = 0.0
                rows[moving, 4] = float(np.mean(np.linalg.norm(np.asarray(entry["trajectory"])[moving, 4:6], axis=1)))
            entry["trajectory"] = rows.tolist()
        extras["info"] = info
        return renamed(ref, sequences), extras

    art = json.loads(json.dumps(renamed(ref)))
    if case in ("shortcut_unscored_heading", "shortcut_global_offset", "shortcut_global_rotation",
                "shortcut_constant", "shortcut_truncate", "shortcut_timestamp", "shortcut_impossible",
                "shortcut_infinite", "shortcut_empty", "shortcut_null"):
        for name in list(art["sequences"]):
            rows = np.asarray(art["sequences"][name]["trajectory"], dtype=np.float64)
            if case == "shortcut_unscored_heading":
                rows[1, 3] = 1e300
            elif case == "shortcut_global_offset":
                rows[:, 1:3] += 1024.0
            elif case == "shortcut_global_rotation":
                a = 0.3
                x, y = rows[:, 1].copy(), rows[:, 2].copy()
                rows[:, 1] = math.cos(a) * x - math.sin(a) * y
                rows[:, 2] = math.sin(a) * x + math.cos(a) * y
                rows[:, 3] += a
            elif case == "shortcut_constant":
                rows[:, 1:] = 0.0
            elif case == "shortcut_truncate":
                rows = rows[:20]
            elif case == "shortcut_timestamp":
                rows[:, 0] = 0.0
            elif case == "shortcut_impossible":
                rows[:, 1:] = -1e30
            elif case == "shortcut_infinite":
                rows[:, 4] = np.inf
            elif case == "shortcut_empty":
                rows = rows[:0]
            elif case == "shortcut_null":
                art["sequences"][name]["trajectory"] = [[float(t)] + [None] * 5 for t in rows[:, 0]]
                continue
            art["sequences"][name]["trajectory"] = rows.tolist()
        extras["nan_ok"] = case == "shortcut_infinite"
        return art, extras
    if case == "shortcut_duplicate":
        extras["files"] = {"method/extra/dro_gd_predictions.json": json.dumps(art)}
        return art, extras
    if case == "shortcut_score_fields":
        art.update(success=True, score=1e300, runtime_s=-1.0)
        for entry in art["sequences"].values():
            entry.update(success=True, translation_error_pct=-1e30, velocity_rmse_mps=0.0)
        extras["files"] = {"scoring/scores_test.json": json.dumps({"score": 1e300, "success": True})}
        return art, extras
    if case in ("shortcut_move_baseline", "shortcut_comparison_compensation"):
        files = {}
        for name in ("dro_g", "dro_d", "fixed_velocity_gyro", "dead_reckoning"):
            files[f"baseline/{name}_predictions.json"] = json.dumps(dict(art, method=name))
        extras["files"] = files
        if case == "shortcut_comparison_compensation":
            return renamed(read_json(COMPARATORS / "fixed_velocity_gyro_comparator.json")), extras
        return art, extras
    if case == "shortcut_visible_answers":
        src = seqs[sorted(n for n, s in seqs.items() if s["split"] == "train")[0]]
        for name in test_names:
            t = seqs[name]["frame_times"]
            rows = np.column_stack([t, src["poses"][: len(t), 1:4], src["velocities"][: len(t)]])
            art["sequences"][name] = {"trajectory": rows.tolist()}
        return art, extras
    if case == "shortcut_rebuild_answers":
        matches = {}
        for seed in range(3000):
            for scenario in ("structured", "tunnel"):
                rngs = gen._spawn_rngs(seed)
                profile = gen.sample_motion_profile(rngs["profile"], scenario)
                fingerprint = (profile["gyro_bias"] + rngs["gyro"].normal(0.0, gen.GYRO_NOISE_STD, 7)).astype(np.float32)
                for name, seq in seqs.items():
                    if name in matches:
                        continue
                    if np.array_equal(fingerprint, seq["gyro_yaw"][:7].astype(np.float32)):
                        sim = gen.simulate_motion(scenario, seed, len(seq["frame_times"]))
                        if np.array_equal(sim["gyro_yaw"].astype(np.float32), seq["gyro_yaw"].astype(np.float32)):
                            matches[name] = (scenario, seed)
        fallback = seqs[sorted(n for n, s in seqs.items() if s["split"] == "train")[0]]
        for name, seq in seqs.items():
            t = seq["frame_times"]
            if name in matches:
                sim = gen.simulate_motion(*matches[name], frames=len(t))
                poses, vel = sim["poses"], sim["velocities"]
            else:
                poses, vel = fallback["poses"][: len(t)], fallback["velocities"][: len(t)]
            art["sequences"][name] = {"trajectory": np.column_stack([t, poses[:, 1:4], vel]).tolist()}
        extras["info"] = {"matched": {k: list(v) for k, v in matches.items()}}
        return art, extras
    if case == "shortcut_fixed_artifact":
        # Plant constant-pose "labels" in a copy of the test inputs and submit
        # matching predictions; the hidden digest must reject the copy.
        with np.load(TEST, allow_pickle=False) as data:
            arrays = {k: data[k] for k in data.files}
        manifest = json.loads(str(arrays["manifest_json"].item()))
        for name in manifest["sequences"]:
            t = arrays[f"{name}_frame_times"]
            arrays[f"{name}_poses"] = np.column_stack([t, np.zeros((len(t), 3))])
            arrays[f"{name}_velocities"] = np.zeros((len(t), 2))
            art["sequences"][name] = {"trajectory": np.column_stack([t, np.zeros((len(t), 5))]).tolist()}
        extras["inputs_override"] = arrays
        return art, extras
    raise ValueError(f"unknown case {case}")


VARIANTS = [
    "reference",
    "better_calibration",
    "better_smoothing",
    "weaker_no_doppler",
    "weaker_doppler_only",
    "simple_baseline",
]
EXPENSIVE = ["weaker_no_gyro_bias", "weaker_legacy_gp_infill"]
SHORTCUTS = [
    "shortcut_calibration_zero_velocity",
    "shortcut_calibration_constant_velocity",
    "shortcut_generator_fit_legacy",
    "shortcut_generator_prior_smoother",
    "shortcut_unscored_heading",
    "shortcut_global_offset",
    "shortcut_global_rotation",
    "shortcut_score_fields",
    "shortcut_move_baseline",
    "shortcut_comparison_compensation",
    "shortcut_visible_answers",
    "shortcut_rebuild_answers",
    "shortcut_fixed_artifact",
    "shortcut_constant",
    "shortcut_truncate",
    "shortcut_timestamp",
    "shortcut_empty",
    "shortcut_null",
    "shortcut_infinite",
    "shortcut_impossible",
    "shortcut_duplicate",
]
# Honest outputs on both splits: score them on train as well.
TRAIN_SCORED = {"reference", "better_calibration", "better_smoothing", "weaker_no_doppler",
                "weaker_doppler_only", "shortcut_generator_fit_legacy", "shortcut_generator_prior_smoother"}


# --------------------------------------------------------------- scoring

def rank(scores: dict, reference: dict, config: dict, rows: list[str] | None) -> dict:
    total = 0.0
    per = {}
    for exp, definition in config["experiments"].items():
        ref_rows = reference["experiments"].get(exp, {}).get("results", {})
        new_rows = scores.get("experiments", {}).get(exp, {}).get("results", {})
        if not ref_rows:
            continue
        sub = 0.0
        for name in rows if rows is not None else list(ref_rows):
            if name not in ref_rows or name not in new_rows:
                continue
            for metric, mdef in definition["metrics"].items():
                if metric in ref_rows[name] and metric in new_rows[name]:
                    sub += definition["weight"] * mdef["coefficient"] * (new_rows[name][metric] - ref_rows[name][metric])
        per[exp] = sub
        total += sub
    return {"rank": total, "per_experiment": per}


def rank_from_per_seq(cand: dict, ref: dict, names: list[str], scen: dict, config: dict) -> float:
    total = 0.0
    for exp, group in EXP_GROUPS.items():
        definition = config["experiments"][exp]
        members = [n for n in names if group is None or scen[n] == group]
        for metric, mdef in definition["metrics"].items():
            key = PER_SEQ_KEY[metric]
            diff = np.mean([cand[n][key] for n in members]) - np.mean([ref[n][key] for n in members])
            total += definition["weight"] * mdef["coefficient"] * float(diff)
    return total


def per_sequence_contributions(cand: dict, ref: dict, scen: dict, config: dict) -> dict:
    names = sorted(scen)
    out = {n: 0.0 for n in names}
    for exp, group in EXP_GROUPS.items():
        definition = config["experiments"][exp]
        members = [n for n in names if group is None or scen[n] == group]
        for metric, mdef in definition["metrics"].items():
            key = PER_SEQ_KEY[metric]
            for n in members:
                out[n] += definition["weight"] * mdef["coefficient"] * (cand[n][key] - ref[n][key]) / len(members)
    return out


def paired_bootstrap(cand: dict, ref: dict, scen: dict, config: dict, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    groups = {g: sorted(n for n in scen if scen[n] == g) for g in ("structured", "tunnel")}
    draws = []
    for _ in range(BOOTSTRAP):
        names = []
        for members in groups.values():
            names += [members[i] for i in rng.integers(0, len(members), len(members))]
        draws.append(rank_from_per_seq(cand, ref, names, scen, config))
    draws = np.asarray(draws)
    contrib = per_sequence_contributions(cand, ref, scen, config)
    point = rank_from_per_seq(cand, ref, sorted(scen), scen, config)
    se = float(np.std(draws, ddof=1))
    return {
        "point": point,
        "se": se,
        "ci95": [float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))],
        "z": point / se if se > 0 else None,
        "sequences_improved": int(sum(v > 1e-12 for v in contrib.values())),
        "sequences_worse": int(sum(v < -1e-12 for v in contrib.values())),
        "per_sequence": contrib,
    }


def make_workspace(case: str, artifact: dict | None, extras: dict, with_train: bool) -> Path:
    ws = WS_ROOT / case
    shutil.rmtree(ws, ignore_errors=True)
    (ws / "scripts").mkdir(parents=True)
    (ws / "data").mkdir()
    shutil.copytree(ROOT / "eval" / "test", ws / "eval" / "test", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(ROOT / "scripts" / "evaluate_test.sh", ws / "scripts" / "evaluate_test.sh")
    if "inputs_override" in extras:
        np.savez_compressed(ws / "data" / "test_inputs.npz", **extras["inputs_override"])
    else:
        (ws / "data" / "test_inputs.npz").symlink_to(TEST)
    if with_train:
        shutil.copytree(ROOT / "eval" / "train", ws / "eval" / "train", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy2(ROOT / "scripts" / "evaluate_train.sh", ws / "scripts" / "evaluate_train.sh")
        (ws / "data" / "train.npz").symlink_to(TRAIN)
    if artifact is not None:
        path = ws / "checkpoints" / "candidate" / "dro_gd_predictions.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(artifact, allow_nan=bool(extras.get("nan_ok"))))
    for rel, text in extras.get("files", {}).items():
        target = ws / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    return ws


def run_case(case: str, ctx: dict, force: bool) -> dict:
    out = CASES_DIR / case
    summary_path = out / "summary.json"
    if summary_path.exists() and not force:
        return read_json(summary_path)
    out.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    artifact, extras = build_case(case, ctx)
    with_train = case in TRAIN_SCORED
    ws = make_workspace(case, artifact, extras, with_train)
    summary: dict = {"case": case, "build_seconds": time.monotonic() - start}
    if "info" in extras:
        summary["info"] = extras["info"]

    log = out / "test.log"
    with log.open("w") as f:
        rc = subprocess.run(["bash", "scripts/evaluate_test.sh"], cwd=ws, stdout=f, stderr=subprocess.STDOUT).returncode
    summary["test_returncode"] = rc
    report = ws / "scoring" / "scores_test.json"
    if rc == 0 and report.exists():
        scores = read_json(report)
        shutil.copy2(report, out / "scores_test.json")
        summary["rank"] = rank(scores, ctx["reference_test"], ctx["config"], ["dro_gd"])
        summary["all_rows_rank"] = rank(scores, ctx["reference_test"], ctx["config"], None)["rank"]
        summary["failed_methods"] = scores["_metadata"]["failed_methods"]
        summary["ignored_artifacts"] = scores["_metadata"]["ignored_artifacts"]
        summary["test_inputs"] = scores["_metadata"]["test_inputs"]
        summary["candidate_results"] = {e: d["results"].get("dro_gd") for e, d in scores["experiments"].items()}
        summary["comparators_unchanged"] = all(
            scores["experiments"][e]["results"].get(c) == ctx["reference_test"]["experiments"][e]["results"].get(c)
            for e in scores["experiments"] for c in ("fixed_velocity_gyro", "dro_d", "dro_g")
        )
    if with_train:
        with (out / "train.log").open("w") as f:
            rc_train = subprocess.run(["bash", "scripts/evaluate_train.sh"], cwd=ws, stdout=f, stderr=subprocess.STDOUT).returncode
        report = ws / "scoring" / "scores_train.json"
        if rc_train == 0 and report.exists():
            scores = read_json(report)
            shutil.copy2(report, out / "scores_train.json")
            summary["train_rank"] = rank(scores, ctx["reference_train"], ctx["config"], ["dro_gd"])
            summary["train_failed_methods"] = scores["_metadata"]["failed_methods"]

    # Paired bootstrap over held-out sequences for valid candidates.
    if artifact is not None and not summary.get("failed_methods"):
        try:
            per_seq = hidden.score_sequences(artifact["sequences"], ctx["labels"])
            summary["bootstrap"] = paired_bootstrap(per_seq, ctx["ref_per_seq"], ctx["scen"], ctx["config"])
            summary["per_sequence_metrics"] = per_seq
        except hidden.InvalidPrediction as exc:
            summary["bootstrap_error"] = str(exc)
    if case.startswith(("better_", "weaker_", "reference")) and artifact is not None:
        (out / "predictions.json").write_text(json.dumps(artifact))
    summary["elapsed_seconds"] = time.monotonic() - start
    summary_path.write_text(json.dumps(summary, indent=2))
    shutil.rmtree(ws, ignore_errors=True)
    r = summary.get("rank", {}).get("rank")
    print(f"{case:42s} rank={r} failed={summary.get('failed_methods')} boot={summary.get('bootstrap', {}).get('se')}", flush=True)
    return summary


def paper_effects(ctx: dict) -> dict:
    """Per-sequence held-out translation error of the frozen rows and the
    reference, with paired differences (the paper's Table I comparison)."""
    rows = {}
    for name in ("fixed_velocity_gyro", "dro_d", "dro_g"):
        frozen = read_json(ROOT / "eval" / "test" / "comparators" / f"{name}.json")
        rows[name] = hidden.score_sequences(frozen["sequences"], ctx["labels"])
    rows["dro_gd"] = ctx["ref_per_seq"]
    out = {"translation_error_pct": {}, "paired_vs_dro_gd": {}}
    for name, per in rows.items():
        out["translation_error_pct"][name] = {n: per[n]["translation_error_pct"] for n in sorted(per)}
    for name in ("fixed_velocity_gyro", "dro_d", "dro_g"):
        for group in ("all", "structured", "tunnel"):
            members = [n for n in sorted(ctx["scen"]) if group == "all" or ctx["scen"][n] == group]
            d = np.array([rows[name][n]["translation_error_pct"] - rows["dro_gd"][n]["translation_error_pct"] for n in members])
            out["paired_vs_dro_gd"][f"{name}/{group}"] = {
                "mean_te_gap_pct": float(d.mean()),
                "se": float(d.std(ddof=1) / math.sqrt(len(d))) if len(d) > 1 else None,
                "dro_gd_better_on": int((d > 0).sum()),
                "n": len(d),
            }
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-expensive", action="store_true")
    parser.add_argument("--force", default="", help="comma-separated cases to recompute ('all' for every case)")
    parser.add_argument("--cases", default="", help="comma-separated subset to run")
    args = parser.parse_args()

    labels_digest, labels = hidden.load_labels()
    ref = read_json(REF_PRED)
    ctx = {
        "ref": ref,
        "seqs": load_inputs(),
        "labels": labels,
        "scen": {n: labels[n]["scenario"] for n in labels},
        "config": read_json(ROOT / "scoring" / "reference.json"),
        "reference_test": read_json(ROOT / "scoring" / "scores_test.json"),
        "reference_train": read_json(ROOT / "scoring" / "scores_train.json"),
    }
    ctx["ref_per_seq"] = hidden.score_sequences(ref["sequences"], labels)

    cases = VARIANTS + SHORTCUTS + ([] if args.skip_expensive else EXPENSIVE)
    if args.cases:
        cases = [c for c in args.cases.split(",") if c]
    force = set(cases) if args.force == "all" else set(c for c in args.force.split(",") if c)
    results = {}
    results_path = HERE / "results.json"
    if results_path.exists():
        results = read_json(results_path).get("cases", {})
    for case in cases:
        try:
            results[case] = run_case(case, ctx, case in force)
        except Exception as exc:  # keep going; record the error
            print(f"{case}: ERROR {exc!r}", flush=True)
            results[case] = {"case": case, "error": repr(exc)}
    summary = {
        "rank_definition": "sum_exp weight * sum_metric coefficient * (candidate - reference), dro_gd row, "
                           "reference = scoring/scores_test.json, weights/coefficients = scoring/reference.json",
        "test_sequences": len(labels),
        "paper_effects": paper_effects(ctx),
        "cases": results,
    }
    results_path.write_text(json.dumps(summary, indent=2))
    print("\nSUMMARY")
    for case, s in results.items():
        r = s.get("rank", {}).get("rank") if isinstance(s.get("rank"), dict) else None
        b = s.get("bootstrap", {})
        tr = s.get("train_rank", {}).get("rank") if isinstance(s.get("train_rank"), dict) else None
        print(f"  {case:42s} test={r!s:24s} train={tr!s:24s} se={b.get('se')} improved={b.get('sequences_improved')} "
              f"failed={s.get('failed_methods') or s.get('error')}")


if __name__ == "__main__":
    main()
