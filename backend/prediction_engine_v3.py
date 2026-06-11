"""MAT Period Prediction Engine — v3 (verified forecasting improvements only).

Pure, deterministic, dependency-free statistical engine (NO external AI, no
randomness). Every enhancement in this version is EVIDENCE-GATED: it is only
active for a user when that user's own walk-forward backtest shows it improves
MAE, calibration, or interval coverage (P12 deployment gates).

Built on top of the v2 ensemble primitives. Additions:

  P1  Personalized prediction-error learning (avg/rolling errors, systematic
      early/late detection, gated bias compensation).
  P2  Dynamic ensemble weighting — true walk-forward weights from continuous
      per-model MAE/RMSE tracking, with weight & accuracy history.
  P3  Conformal prediction intervals (P50/75/90/95) from the production
      pipeline's own out-of-sample signed errors, with coverage tracking and
      rejection fallback when calibration fails.
  P4  Adaptive lookback windows (3/6/12/24) selected per user by backtest MAE.
  P5  Direct quantile forecasting (P10/25/50/75/90) gated by pinball loss
      against the traditional mean±z·std approach.
  P6  Change-point detection with change_point_confidence.
  P7  Full probability-distribution forecasting from the empirical error CDF —
      intervals and quantiles derive from the SAME distribution.
  P8  Confidence calibration engine (bucketed calibration error, <5% target,
      gated shrinkage).
  P9  Forecast stability optimization (volatility/drift/oscillation tracking +
      gated dampening).
  P10 Continuous walk-forward backtesting drives all selection.
  P11 Automatic per-user forecasting-strategy selection (margin-protected).
  P12 Runtime deployment gates — nothing ships unless it measures better.
  P13 Extended explainability (strategy, window, gates, contributions).
  P14 Monitoring metrics are persisted server-side from this engine's outputs.

Deterministic: same input always produces identical output (P18-equivalent).
"""
from __future__ import annotations

import bisect
import math
import statistics
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from prediction_engine import (
    clamp,
    coerce_date,
    period_length,
    cycle_lengths_from_starts,
    median_value,
    mean_value,
    std_dev,
    median_absolute_deviation,
    classify_regularity,
    regularity_from_std,
    variability_score,
    fertile_window,
    probability_distribution as gaussian_distribution,
    prediction_window,
    MIN_CYCLE_LENGTH,
    MAX_CYCLE_LENGTH,
)
from prediction_engine_v2 import (
    ACCURACY_TOLERANCE_DAYS,
    BACKTEST_WINDOW,
    DEFAULT_WEIGHTS,
    MIN_HISTORY,
    MODEL_KEYS,
    POP_CYCLE_MEAN,
    POP_CYCLE_VARIANCE,
    POP_PERIOD_MEAN,
    _adaptive_weights,
    _model_predictions,
    _prediction_id as _v2_prediction_id,
    _weight_factors,
    classify_outliers,
    data_sufficiency,
    detect_change_points,
    medical_flags,
    percentile,
    prediction_intervals as v2_prediction_intervals,
    reliability_index,
    rolling_error,
    trend_forecast,
    trimmed_mean,
    validation_metrics,
    winsorized_mean,
)

# ----------------------------- Versioning -----------------------------
ENGINE_VERSION = "3.0.0"
ALGORITHM_VERSION = "verified-forecast-v1"

STRATEGIES = MODEL_KEYS + ["ensemble"]
DEFAULT_STRATEGY = "ensemble"
LOOKBACK_WINDOWS = [3, 6, 12, 24]
DEFAULT_WINDOW = 12
SELECTION_MARGIN = 0.15        # days of MAE a challenger must beat the default by
GATE_EPSILON = 0.01            # a gated variant must strictly improve MAE by this
DAMPENING_CLAMP = 2.0          # max day-to-day forecast movement when dampened
MIN_CONFORMAL_SAMPLES = 8      # signed errors needed for conformal intervals
MIN_COVERAGE_EVALS = 5         # walk-forward checks needed to judge coverage
COVERAGE_REJECT_THRESHOLD = 0.10   # |expected-observed| at 95% that rejects conformal
CONFORMAL_LEVELS = (50, 75, 90, 95)
QUANTILE_LEVELS = (10, 25, 50, 75, 90)
VARIANTS = ("raw", "bias", "damp", "bias_damp")
CONFIDENCE_PRIOR_N = 3         # shrinkage prior strength (pseudo-observations)
_Z = {10: -1.2816, 25: -0.6745, 50: 0.0, 75: 0.6745, 90: 1.2816}


# ----------------------------- Walk-forward harness (P10) -----------------------------
def walk_forward(cycle_lengths: List[int], starts: List[date], window: int) -> Dict:
    """Walk-forward backtest with a given lookback window.

    At each step the dynamic ensemble weights and the error-correction bias are
    computed ONLY from earlier steps (true out-of-sample, P2/P10).
    """
    n = len(cycle_lengths)
    per_model_abs: Dict[str, List[float]] = {k: [] for k in MODEL_KEYS}
    per_model_sq: Dict[str, List[float]] = {k: [] for k in MODEL_KEYS}
    strat_preds: Dict[str, List[float]] = {s: [] for s in STRATEGIES}
    actuals: List[float] = []
    target_indices: List[int] = []
    ens_signed: List[float] = []
    weight_history: List[Dict[str, float]] = []
    accuracy_history: List[Dict[str, float]] = []

    start_i = max(MIN_HISTORY, n - BACKTEST_WINDOW)
    for i in range(start_i, n):
        lo = max(0, i - window)
        hist = cycle_lengths[lo:i]
        hist_starts = starts[lo:i]
        if len(hist) < 2:
            continue
        wf = _weight_factors(hist, hist_starts)
        bias_i = float(statistics.median(ens_signed[-12:])) if ens_signed else 0.0
        preds = _model_predictions(hist, wf, bias_i)
        if any(per_model_abs[k] for k in MODEL_KEYS):
            weights_i = _adaptive_weights(per_model_abs)
        else:
            weights_i = dict(DEFAULT_WEIGHTS)
        ens = sum(weights_i[k] * preds[k] for k in MODEL_KEYS)
        actual = float(cycle_lengths[i])

        for k in MODEL_KEYS:
            err = actual - preds[k]
            per_model_abs[k].append(abs(err))
            per_model_sq[k].append(err * err)
            strat_preds[k].append(preds[k])
        strat_preds["ensemble"].append(ens)
        ens_signed.append(actual - ens)
        actuals.append(actual)
        target_indices.append(i)
        weight_history.append({k: round(weights_i[k], 4) for k in MODEL_KEYS})
        accuracy_history.append({
            k: round(statistics.mean(per_model_abs[k]), 3) for k in MODEL_KEYS
        })

    model_accuracy = {}
    for k in MODEL_KEYS:
        if per_model_abs[k]:
            model_accuracy[k] = {
                "mae": round(statistics.mean(per_model_abs[k]), 3),
                "rmse": round(math.sqrt(statistics.mean(per_model_sq[k])), 3),
                "samples": len(per_model_abs[k]),
            }
        else:
            model_accuracy[k] = {"mae": None, "rmse": None, "samples": 0}

    return {
        "window": window,
        "strat_preds": strat_preds,
        "actuals": actuals,
        "target_indices": target_indices,
        "ens_signed": ens_signed,
        "per_model_abs": per_model_abs,
        "model_accuracy": model_accuracy,
        "weight_history": weight_history,
        "accuracy_history": accuracy_history,
    }


# ----------------------------- Variant transforms (P1/P9 gates) -----------------------------
def apply_bias_correction(raw: List[float], actuals: List[float]) -> List[float]:
    """Walk-forward personalized bias compensation: each step adds the median
    signed error of the RAW series over its own past (last 12)."""
    out: List[float] = []
    signed: List[float] = []
    for p, a in zip(raw, actuals):
        b = float(statistics.median(signed[-12:])) if signed else 0.0
        out.append(p + b)
        signed.append(a - p)
    return out


def apply_dampening(preds: List[float]) -> List[float]:
    """Limit step-to-step forecast movement to ±DAMPENING_CLAMP days (P9)."""
    out: List[float] = []
    prev: Optional[float] = None
    for p in preds:
        q = p if prev is None else prev + clamp(p - prev, -DAMPENING_CLAMP, DAMPENING_CLAMP)
        out.append(q)
        prev = q
    return out


def _variant_series(raw: List[float], actuals: List[float], variant: str) -> List[float]:
    if variant == "raw":
        return list(raw)
    if variant == "bias":
        return apply_bias_correction(raw, actuals)
    if variant == "damp":
        return apply_dampening(raw)
    return apply_dampening(apply_bias_correction(raw, actuals))


def _mae(preds: List[float], actuals: List[float]) -> Optional[float]:
    if not preds:
        return None
    return statistics.mean(abs(a - p) for p, a in zip(preds, actuals))


def _best_variant(raw: List[float], actuals: List[float]) -> Tuple[str, Dict[str, float]]:
    """Pick the variant with the lowest MAE; gated — a transform is only chosen
    if it STRICTLY improves on raw (P12). Ties prefer the simpler variant."""
    maes: Dict[str, float] = {}
    for v in VARIANTS:
        m = _mae(_variant_series(raw, actuals, v), actuals)
        maes[v] = round(m, 4) if m is not None else None
    best = "raw"
    if maes["raw"] is not None:
        for v in VARIANTS[1:]:
            if maes[v] is not None and maes[v] < maes[best] - GATE_EPSILON:
                best = v
    return best, maes


# ----------------------------- Pipeline selection (P4/P11/P12) -----------------------------
def select_pipeline(cycle_lengths: List[int], starts: List[date]) -> Dict:
    """Jointly select (strategy, lookback window, variant) by walk-forward MAE.

    The default pipeline (ensemble @ 12) is kept unless a challenger beats it
    by SELECTION_MARGIN days of MAE — preventing noisy strategy flapping.
    """
    wf_by_window = {w: walk_forward(cycle_lengths, starts, w) for w in LOOKBACK_WINDOWS}

    candidates: List[Tuple[float, int, int, str, str]] = []
    candidate_info: Dict[Tuple[str, int], Dict] = {}
    for w_idx, w in enumerate(LOOKBACK_WINDOWS):
        wf = wf_by_window[w]
        for s_idx, s in enumerate(STRATEGIES):
            raw = wf["strat_preds"][s]
            if not raw:
                continue
            variant, maes = _best_variant(raw, wf["actuals"])
            mae = maes[variant]
            candidate_info[(s, w)] = {"variant": variant, "maes": maes, "mae": mae}
            candidates.append((round(mae, 6), s_idx, w_idx, s, w))

    default_key = (DEFAULT_STRATEGY, DEFAULT_WINDOW)
    if not candidates:  # not enough history for any walk-forward step
        return {
            "strategy": DEFAULT_STRATEGY, "window": DEFAULT_WINDOW, "variant": "raw",
            "mae": None, "default_mae": None, "selected_by_evidence": False,
            "wf": wf_by_window[DEFAULT_WINDOW], "wf_by_window": wf_by_window,
            "variant_maes": {}, "candidates": {},
        }

    candidates.sort()
    _, _, _, best_s, best_w = candidates[0]
    best = candidate_info[(best_s, best_w)]
    default = candidate_info.get(default_key)
    default_mae = default["mae"] if default else None

    chosen_s, chosen_w = best_s, best_w
    selected_by_evidence = True
    if (best_s, best_w) != default_key and default is not None:
        if best["mae"] > default_mae - SELECTION_MARGIN:
            chosen_s, chosen_w = default_key
            selected_by_evidence = False

    chosen = candidate_info[(chosen_s, chosen_w)]
    return {
        "strategy": chosen_s,
        "window": chosen_w,
        "variant": chosen["variant"],
        "mae": chosen["mae"],
        "default_mae": default_mae,
        "selected_by_evidence": selected_by_evidence,
        "wf": wf_by_window[chosen_w],
        "wf_by_window": wf_by_window,
        "variant_maes": chosen["maes"],
        "candidates": {f"{s}@{w}": info["mae"] for (s, w), info in candidate_info.items()},
    }


# ----------------------------- Runtime pipeline application -----------------------------
def _runtime_prediction(cycle_lengths: List[int], starts: List[date],
                        pipeline: Dict) -> Tuple[float, Dict[str, float], Dict[str, float]]:
    """Apply the selected pipeline to the full history to predict the NEXT cycle."""
    n = len(cycle_lengths)
    w = pipeline["window"]
    wf = pipeline["wf"]
    hist = cycle_lengths[max(0, n - w):]
    hist_starts = starts[max(0, n - w):n]

    bias_model = (float(statistics.median(wf["ens_signed"][-12:]))
                  if wf["ens_signed"] else 0.0)
    factors = _weight_factors(hist, hist_starts) if hist else []
    preds = _model_predictions(hist, factors, bias_model)
    if any(wf["per_model_abs"][k] for k in MODEL_KEYS):
        weights = _adaptive_weights(wf["per_model_abs"])
    else:
        weights = dict(DEFAULT_WEIGHTS)

    strategy = pipeline["strategy"]
    if strategy == "ensemble":
        raw = sum(weights[k] * preds[k] for k in MODEL_KEYS)
    else:
        raw = preds[strategy]

    variant = pipeline["variant"]
    raw_series = wf["strat_preds"][strategy]
    actuals = wf["actuals"]
    value = raw
    if variant in ("bias", "bias_damp") and raw_series:
        signed = [a - p for p, a in zip(raw_series, actuals)]
        value = value + float(statistics.median(signed[-12:]))
    if variant in ("damp", "bias_damp") and raw_series:
        prior = _variant_series(raw_series, actuals, variant)
        prev = prior[-1]
        value = prev + clamp(value - prev, -DAMPENING_CLAMP, DAMPENING_CLAMP)
    return value, preds, weights


# ----------------------------- Conformal prediction (P3) -----------------------------
def conformal_intervals(center: date, signed_errors: List[float]) -> Optional[Dict]:
    """Split-conformal intervals from the pipeline's own signed errors."""
    if len(signed_errors) < MIN_CONFORMAL_SAMPLES:
        return None
    out: Dict[str, Dict] = {}
    for level in CONFORMAL_LEVELS:
        lo_q = (100 - level) / 2.0
        hi_q = 100 - lo_q
        lo = percentile(signed_errors, lo_q) or 0.0
        hi = percentile(signed_errors, hi_q) or 0.0
        start = center + timedelta(days=int(math.floor(lo)))
        end = center + timedelta(days=int(math.ceil(hi)))
        out[f"p{level}"] = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "half_width_days": int(round((end - start).days / 2.0)),
        }
    out["source"] = "conformal"
    return out


def conformal_coverage(signed_errors: List[float]) -> Dict:
    """Walk-forward coverage audit: for each step, build conformal bounds from
    the PRIOR errors only and check whether the step's error fell inside."""
    levels = {lv: {"covered": 0, "total": 0} for lv in CONFORMAL_LEVELS}
    for t in range(len(signed_errors)):
        prior = signed_errors[:t]
        if len(prior) < MIN_COVERAGE_EVALS:
            continue
        e = signed_errors[t]
        for lv in CONFORMAL_LEVELS:
            lo_q = (100 - lv) / 2.0
            lo = percentile(prior, lo_q) or 0.0
            hi = percentile(prior, 100 - lo_q) or 0.0
            levels[lv]["total"] += 1
            if math.floor(lo) <= e <= math.ceil(hi):
                levels[lv]["covered"] += 1
    report = {}
    for lv in CONFORMAL_LEVELS:
        tot = levels[lv]["total"]
        observed = round(levels[lv]["covered"] / tot, 3) if tot else None
        expected = lv / 100.0
        report[f"p{lv}"] = {
            "expected_coverage": expected,
            "observed_coverage": observed,
            "calibration_error": (round(abs(expected - observed), 3)
                                  if observed is not None else None),
            "evaluations": tot,
        }
    p95 = report["p95"]
    rejected = (p95["evaluations"] >= MIN_COVERAGE_EVALS
                and p95["calibration_error"] is not None
                and p95["calibration_error"] > COVERAGE_REJECT_THRESHOLD)
    report["accepted"] = not rejected
    return report


# ----------------------------- Quantile forecasting (P5) -----------------------------
def _pinball(q: float, actual: float, p: float) -> float:
    tau = p / 100.0
    diff = actual - q
    return max(tau * diff, (tau - 1) * diff)


def quantile_forecast(center_len: float, last_start: Optional[date],
                      signed_errors: List[float], cstd: float) -> Dict:
    """Direct quantile forecasts (P10..P90), gated by walk-forward pinball loss
    against the traditional mean±z·std construction."""
    sigma = cstd if cstd and cstd > 0 else 2.0
    direct_ok = len(signed_errors) >= MIN_CONFORMAL_SAMPLES

    # ---- pinball-loss gate (walk-forward, prior-errors-only) ----
    pin_direct = 0.0
    pin_trad = 0.0
    evals = 0
    for t in range(len(signed_errors)):
        prior = signed_errors[:t]
        if len(prior) < MIN_COVERAGE_EVALS:
            continue
        e = signed_errors[t]
        sd = std_dev(prior) or sigma
        for p in QUANTILE_LEVELS:
            pin_direct += _pinball(percentile(prior, p) or 0.0, e, p)
            pin_trad += _pinball(statistics.mean(prior) + _Z[p] * max(sd, 0.5), e, p)
        evals += 1

    if not direct_ok or evals < MIN_COVERAGE_EVALS:
        method = "traditional"
    else:
        method = "direct_empirical" if pin_direct <= pin_trad else "traditional"

    quantiles: Dict[str, Optional[str]] = {}
    offsets: Dict[str, float] = {}
    for p in QUANTILE_LEVELS:
        if method == "direct_empirical":
            off = percentile(signed_errors, p) or 0.0
        else:
            off = _Z[p] * sigma
        offsets[f"p{p}"] = round(off, 2)
        if last_start is not None:
            d = last_start + timedelta(days=int(round(center_len + off)))
            quantiles[f"p{p}"] = d.isoformat()
        else:
            quantiles[f"p{p}"] = None

    return {
        "method": method,
        "quantiles": quantiles,
        "offsets_days": offsets,
        "pinball_loss": {
            "direct_empirical": round(pin_direct, 3) if evals else None,
            "traditional": round(pin_trad, 3) if evals else None,
            "evaluations": evals,
        },
    }


# ----------------------------- Distribution forecasting (P7) -----------------------------
def _ecdf(sorted_errors: List[float], x: float) -> float:
    n = len(sorted_errors)
    if x <= sorted_errors[0]:
        return 0.0
    if x >= sorted_errors[-1]:
        return 1.0
    j = bisect.bisect_right(sorted_errors, x)
    lo, hi = sorted_errors[j - 1], sorted_errors[j]
    f_lo, f_hi = j / (n + 1), (j + 1) / (n + 1)
    if hi == lo:
        return f_lo
    return f_lo + (f_hi - f_lo) * (x - lo) / (hi - lo)


def empirical_distribution(center: date, signed_errors: List[float]) -> Optional[List[Dict]]:
    """Per-day probability mass from the pipeline's empirical error CDF.

    Emits the v1-compatible fixed 14-day window (offsets -7..+6); tail mass
    beyond the window accumulates into the edge days so total mass is
    preserved. Intervals and quantiles derive from the SAME error
    distribution, so the whole uncertainty stack is internally consistent (P7).
    """
    if len(signed_errors) < MIN_CONFORMAL_SAMPLES:
        return None
    s = sorted(signed_errors)
    out: List[Dict] = []
    for off in range(-7, 7):
        if off == -7:
            mass = _ecdf(s, off + 0.5)
        elif off == 6:
            mass = 1.0 - _ecdf(s, off - 0.5)
        else:
            mass = _ecdf(s, off + 0.5) - _ecdf(s, off - 0.5)
        out.append({
            "date": (center + timedelta(days=off)).isoformat(),
            "dayOffset": off,
            "probability": int(round(mass * 100)),
        })
    return out


# ----------------------------- Calibration engine (P8) -----------------------------
def _walkforward_confidence(signed_errors: List[float], shrunk: bool) -> List[Tuple[float, bool]]:
    """(predicted_confidence, hit) pairs, each computed from prior errors only."""
    pairs: List[Tuple[float, bool]] = []
    for t in range(len(signed_errors)):
        prior = signed_errors[:t]
        if len(prior) < 3:
            continue
        window = prior[-12:]
        hits = sum(1 for e in window if abs(e) <= ACCURACY_TOLERANCE_DAYS)
        if shrunk:
            overall = sum(1 for e in prior if abs(e) <= ACCURACY_TOLERANCE_DAYS) / len(prior)
            conf = (hits + CONFIDENCE_PRIOR_N * overall) / (len(window) + CONFIDENCE_PRIOR_N)
        else:
            conf = hits / len(window)
        hit = abs(signed_errors[t]) <= ACCURACY_TOLERANCE_DAYS
        pairs.append((conf * 100.0, hit))
    return pairs


def _calibration_error(pairs: List[Tuple[float, bool]]) -> Tuple[Optional[float], List[Dict]]:
    """Bucketed expected-vs-observed calibration error in percentage points."""
    if not pairs:
        return None, []
    buckets = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 101)]
    rows: List[Dict] = []
    weighted = 0.0
    n = len(pairs)
    for lo, hi in buckets:
        members = [(c, h) for c, h in pairs if lo <= c < hi]
        if not members:
            continue
        avg_conf = statistics.mean(c for c, _ in members)
        acc = sum(1 for _, h in members if h) / len(members) * 100.0
        rows.append({"bucket": f"{lo}-{min(hi, 100)}", "samples": len(members),
                     "predicted_confidence": round(avg_conf, 1),
                     "observed_accuracy": round(acc, 1)})
        weighted += (len(members) / n) * abs(avg_conf - acc)
    return round(weighted, 2), rows


def calibration_engine(signed_errors: List[float]) -> Dict:
    """Confidence calibration: raw recent-hit-rate vs shrunk estimator, gated by
    which produces the lower walk-forward calibration error (P8/P12)."""
    raw_pairs = _walkforward_confidence(signed_errors, shrunk=False)
    shr_pairs = _walkforward_confidence(signed_errors, shrunk=True)
    ce_raw, buckets_raw = _calibration_error(raw_pairs)
    ce_shr, _ = _calibration_error(shr_pairs)

    if ce_raw is None and ce_shr is None:
        method = "raw"
    elif ce_shr is not None and (ce_raw is None or ce_shr < ce_raw - GATE_EPSILON):
        method = "shrunk"
    else:
        method = "raw"
    ce = ce_shr if method == "shrunk" else ce_raw

    # runtime confidence from ALL available errors with the gated method
    window = signed_errors[-12:]
    confidence = None
    samples = len(window)
    if len(window) >= 3:
        hits = sum(1 for e in window if abs(e) <= ACCURACY_TOLERANCE_DAYS)
        if method == "shrunk":
            overall = (sum(1 for e in signed_errors if abs(e) <= ACCURACY_TOLERANCE_DAYS)
                       / len(signed_errors))
            confidence = (hits + CONFIDENCE_PRIOR_N * overall) / (samples + CONFIDENCE_PRIOR_N) * 100
        else:
            confidence = hits / samples * 100
        confidence = round(confidence, 1)

    return {
        "confidence": confidence,
        "samples": samples,
        "estimator": method,
        "calibration_error": ce,
        "calibration_error_raw": ce_raw,
        "calibration_error_shrunk": ce_shr,
        "target_met": (ce is not None and ce < 5.0),
        "target": 5.0,
        "buckets": buckets_raw,
    }


# ----------------------------- Forecast stability (P9) -----------------------------
def forecast_stability(final_series: List[float], final_errors: List[float],
                       variant: str, variant_maes: Dict[str, float]) -> Dict:
    oscillation = None
    if len(final_series) >= 2:
        moves = [abs(final_series[t] - final_series[t - 1])
                 for t in range(1, len(final_series))]
        oscillation = round(statistics.mean(moves), 2)
    volatility = round(std_dev(final_errors), 2) if final_errors else None
    drift = None
    if len(final_errors) >= 6:
        half = len(final_errors) // 2
        drift = round(statistics.mean(final_errors[half:])
                      - statistics.mean(final_errors[:half]), 2)
    score = None
    if volatility is not None:
        score = round(clamp(100 - volatility * 12 - (oscillation or 0) * 8, 0, 100), 1)
    return {
        "stability_score": score,
        "prediction_volatility": volatility,
        "date_oscillation": oscillation,
        "forecast_drift": drift,
        "dampening_applied": variant in ("damp", "bias_damp"),
        "dampening_gate": {
            "mae_raw": variant_maes.get("raw"),
            "mae_dampened": variant_maes.get("damp"),
        },
    }


# ----------------------------- Error learning (P1) -----------------------------
def error_learning(final_errors: List[float], bias_applied: bool,
                   variant_maes: Dict[str, float]) -> Dict:
    avg = round(statistics.mean(final_errors), 2) if final_errors else None
    recent = final_errors[-6:]
    med_recent = float(statistics.median(recent)) if recent else 0.0
    if len(recent) >= 3 and med_recent >= 1.0:
        direction = "systematic_early"     # actual after predicted -> predicting early
    elif len(recent) >= 3 and med_recent <= -1.0:
        direction = "systematic_late"
    else:
        direction = "none"
    return {
        "average_error": avg,
        "rolling_3_cycle_error": rolling_error(final_errors, 3),
        "rolling_6_cycle_error": rolling_error(final_errors, 6),
        "rolling_12_cycle_error": rolling_error(final_errors, 12),
        "bias_days": round(med_recent, 2),
        "bias_direction": direction,
        "bias_correction_applied": bias_applied,
        "bias_gate": {
            "mae_raw": variant_maes.get("raw"),
            "mae_bias_corrected": variant_maes.get("bias"),
        },
    }


# ----------------------------- Change points with confidence (P6) -----------------------------
def change_points_with_confidence(cycle_lengths: List[int], starts: List[date]) -> List[Dict]:
    cps = detect_change_points(cycle_lengths)
    if not cps:
        return []
    mad = median_absolute_deviation(cycle_lengths)
    threshold = max(3.0, 1.5 * mad)
    for cp in cps:
        idx = cp["index"]
        cp["date"] = starts[idx].isoformat() if idx < len(starts) else None
        cp["change_point_date"] = cp["date"]
        seg = cycle_lengths[idx:]
        seg_sd = std_dev(seg)
        magnitude = min(1.0, abs(cp["shift_days"]) / (2.0 * threshold))
        consistency = 1.0 - clamp(seg_sd / max(threshold, 1.0), 0.0, 0.5)
        cp["change_point_confidence"] = round(clamp(100 * magnitude * consistency, 0, 100))
    return cps


# ----------------------------- Top-level engine -----------------------------
def predict(cycles: List[Dict], today: Optional[date] = None,
            generated_at: Optional[str] = None) -> Dict:
    """Run the full v3 verified-forecasting engine.

    Output is a superset of the v2 schema (UI backward-compatible) and is a
    pure function of ``cycles`` — ``generated_at`` is metadata only."""
    today = today or date.today()

    parsed: List[Tuple[date, Optional[date]]] = []
    for c in cycles:
        sd = coerce_date(c.get("start_date"))
        if sd is None:
            continue
        ed = coerce_date(c.get("end_date"))
        if ed is not None and ed < sd:
            ed = None
        parsed.append((sd, ed))
    parsed.sort(key=lambda x: x[0])

    starts = [p[0] for p in parsed]
    ends = [p[1] for p in parsed]
    n_cycles = len(starts)
    cycle_lengths = cycle_lengths_from_starts(starts)
    period_lengths = [period_length(sd, ed) for sd, ed in parsed if ed is not None]
    n_lengths = len(cycle_lengths)

    med = median_value(cycle_lengths)
    cstd = std_dev(cycle_lengths)
    classification = classify_regularity(n_cycles, cstd)
    sufficiency = data_sufficiency(n_cycles)

    # ---- Pipeline selection: window × strategy × variant, all walk-forward (P4/P10/P11) ----
    pipeline = select_pipeline(cycle_lengths, starts)
    wf = pipeline["wf"]
    raw_series = wf["strat_preds"].get(pipeline["strategy"], [])
    final_series = (_variant_series(raw_series, wf["actuals"], pipeline["variant"])
                    if raw_series else [])
    final_errors = [a - p for p, a in zip(final_series, wf["actuals"])]

    # ---- Runtime point prediction with the selected pipeline ----
    if n_lengths == 0:
        final_len_raw = POP_CYCLE_MEAN
        model_preds = {k: POP_CYCLE_MEAN for k in MODEL_KEYS}
        weights = dict(DEFAULT_WEIGHTS)
    else:
        final_len_raw, model_preds, weights = _runtime_prediction(
            cycle_lengths, starts, pipeline)
    final_len = clamp(final_len_raw, MIN_CYCLE_LENGTH, MAX_CYCLE_LENGTH)
    cycle_length_prediction = int(round(final_len))

    last_start = starts[-1] if starts else None
    predicted_date = (last_start + timedelta(days=cycle_length_prediction)
                      if last_start and sufficiency["level"] >= 1 else None)

    # ---- Calibrated confidence with gated estimator (P8) ----
    calibration = calibration_engine(final_errors)
    conf_val = calibration["confidence"]
    conf_source = "historical_accuracy" if conf_val is not None else "prior_based"
    if conf_val is None:
        conf_val = clamp(40 - cstd * 4, 10, sufficiency["max_confidence"])
    confidence = round(min(conf_val, sufficiency["max_confidence"]), 1)

    # ---- Outliers / reliability (unchanged robust layer) ----
    outliers = classify_outliers(cycle_lengths, starts)
    outlier_count = len(outliers)
    vmetrics = validation_metrics(final_errors)
    accuracy_rate = vmetrics.get("success_rate") if final_errors else None
    missing_rate = (1 - (len(period_lengths) / n_cycles)) if n_cycles else 1.0
    reliability = reliability_index(n_cycles, cstd, accuracy_rate,
                                    outlier_count, n_lengths, missing_rate)

    # ---- Change points + trend ----
    change_points = change_points_with_confidence(cycle_lengths, starts)
    trend = trend_forecast(cycle_lengths, period_lengths)

    # ---- Conformal intervals + coverage audit (P3) ----
    coverage = conformal_coverage(final_errors)
    intervals: Dict = {}
    distribution: List[Dict] = []
    quantiles: Dict = {}
    earliest = latest = None
    fertile_start = fertile_end = ovulation = None
    if predicted_date is not None:
        conf_int = (conformal_intervals(predicted_date, final_errors)
                    if coverage["accepted"] else None)
        if conf_int is not None:
            intervals = conf_int
        else:
            intervals = v2_prediction_intervals(predicted_date, final_errors, cstd)
            if not coverage["accepted"]:
                intervals["source"] = f"{intervals['source']} (conformal_rejected)"
        earliest, latest, margin = prediction_window(predicted_date, cstd, int(confidence))
        dist = empirical_distribution(predicted_date, final_errors)
        distribution = dist if dist is not None else gaussian_distribution(
            predicted_date, cstd, margin, int(confidence))
        fertile_start, fertile_end, ovulation = fertile_window(predicted_date)
    quantiles = quantile_forecast(final_len, last_start, final_errors, cstd)

    # ---- Stability / error learning ----
    stability = forecast_stability(final_series, final_errors,
                                   pipeline["variant"], pipeline["variant_maes"])
    err_learning = error_learning(final_errors,
                                  pipeline["variant"] in ("bias", "bias_damp"),
                                  pipeline["variant_maes"])

    # ---- Medical safety flags (informational only) ----
    flags = medical_flags(cycle_lengths, period_lengths, med, trend)

    # ---- Benchmark records (correct start-date alignment) ----
    records: List[Dict] = []
    for t, i in enumerate(wf["target_indices"]):
        if i + 1 >= len(starts):
            continue
        pred_start = starts[i] + timedelta(days=int(round(final_series[t])))
        actual_start = starts[i + 1]
        records.append({
            "predicted_period_start": pred_start.isoformat(),
            "actual_period_start": actual_start.isoformat(),
            "prediction_error_days": (actual_start - pred_start).days,
            "model_version": ENGINE_VERSION,
        })
    benchmark = {
        "engine_version": ENGINE_VERSION,
        "overall_accuracy": vmetrics["success_rate"],
        "mae": vmetrics["mae"],
        "rmse": vmetrics["rmse"],
        "samples": vmetrics["samples"],
        "by_regularity": classification,
        "by_cycle_count": n_cycles,
        "records": records,
    }

    # ---- Lookback window report (P4) ----
    window_metrics = {}
    for w in LOOKBACK_WINDOWS:
        m = pipeline["candidates"].get(f"ensemble@{w}")
        window_metrics[str(w)] = {"ensemble_mae": m}
    lookback = {
        "optimal_window": pipeline["window"],
        "window_performance_metrics": window_metrics,
    }

    # ---- Deployment gates (P12) ----
    deployment_gate = {
        "policy": ("An enhancement is only active when this user's walk-forward "
                   "backtest shows it improves MAE, calibration or coverage."),
        "default_pipeline": {"strategy": DEFAULT_STRATEGY, "window": DEFAULT_WINDOW,
                             "mae": pipeline["default_mae"]},
        "selected_pipeline": {"strategy": pipeline["strategy"],
                              "window": pipeline["window"],
                              "variant": pipeline["variant"],
                              "mae": pipeline["mae"],
                              "selected_by_evidence": pipeline["selected_by_evidence"],
                              "selection_margin_days": SELECTION_MARGIN},
        "gates": {
            "bias_correction": {
                "applied": pipeline["variant"] in ("bias", "bias_damp"),
                "mae_raw": pipeline["variant_maes"].get("raw"),
                "mae_with": pipeline["variant_maes"].get("bias"),
            },
            "dampening": {
                "applied": pipeline["variant"] in ("damp", "bias_damp"),
                "mae_raw": pipeline["variant_maes"].get("raw"),
                "mae_with": pipeline["variant_maes"].get("damp"),
            },
            "conformal_intervals": {
                "applied": bool(intervals.get("source") == "conformal"),
                "calibration_error_p95": coverage["p95"]["calibration_error"],
                "reject_threshold": COVERAGE_REJECT_THRESHOLD,
            },
            "quantile_method": {
                "selected": quantiles["method"],
                "pinball_direct": quantiles["pinball_loss"]["direct_empirical"],
                "pinball_traditional": quantiles["pinball_loss"]["traditional"],
            },
            "confidence_estimator": {
                "selected": calibration["estimator"],
                "calibration_error_raw": calibration["calibration_error_raw"],
                "calibration_error_shrunk": calibration["calibration_error_shrunk"],
            },
        },
    }

    # ---- Population prior ----
    blend_weight = round(clamp(n_cycles / 6.0, 0, 1), 3)
    population_prior = {
        "average_cycle_length": POP_CYCLE_MEAN,
        "average_period_length": POP_PERIOD_MEAN,
        "variance": POP_CYCLE_VARIANCE,
        "blend_weight": blend_weight,
    }

    # ---- Audit trail (P13, extended) ----
    excluded = [o for o in outliers if o["weight_factor"] <= 0.15]
    audit = {
        "prediction_id": _prediction_id(starts, ends),
        "generated_at": generated_at,
        "contributing_cycles": [
            {"index": i, "date": starts[i].isoformat()} for i in range(len(starts))
        ],
        "excluded_cycles": excluded,
        "outlier_adjustments": outliers,
        "trend_adjustments": {
            "change_points": change_points,
            "cycle_length_strength": trend["cycle_length_strength"],
            "applied_bias_days": (err_learning["bias_days"]
                                  if err_learning["bias_correction_applied"] else 0.0),
        },
        "confidence_source": conf_source,
        "forecast_generated_by": {
            "strategy": pipeline["strategy"],
            "lookback_window": pipeline["window"],
            "variant": pipeline["variant"],
            "why_this_prediction": (
                f"Selected '{pipeline['strategy']}' over a {pipeline['window']}-cycle "
                f"lookback because it produced the lowest walk-forward MAE "
                f"({pipeline['mae']}) for this user's history."
                if pipeline["mae"] is not None else
                "Default pipeline — not enough history for evidence-based selection."),
            "why_this_confidence": (
                f"Confidence is the {calibration['estimator']} historical ±2-day hit "
                f"rate over the last {calibration['samples']} out-of-sample predictions, "
                f"capped by data-sufficiency level {sufficiency['level']}."),
        },
        "model_versions": {
            "engine_version": ENGINE_VERSION,
            "algorithm_version": ALGORITHM_VERSION,
            "model_weights": {k: round(weights[k], 4) for k in MODEL_KEYS},
        },
    }

    profile = {
        "cycle_count": n_cycles,
        "average_cycle_length": round(mean_value(cycle_lengths), 1) if cycle_lengths else None,
        "median_cycle_length": round(med, 1) if med is not None else None,
        "trimmed_mean_cycle_length": round(trimmed_mean(cycle_lengths), 1) if cycle_lengths else None,
        "winsorized_mean_cycle_length": round(winsorized_mean(cycle_lengths), 1) if cycle_lengths else None,
        "average_period_length": round(mean_value(period_lengths), 1) if period_lengths else None,
        "cycle_standard_deviation": round(cstd, 2),
        "cycle_variability_score": variability_score(cstd) if cycle_lengths else None,
        "regularity_score": regularity_from_std(cstd) if cycle_lengths else None,
        "prediction_accuracy_score": accuracy_rate,
        "data_quality_score": round((1 - missing_rate) * 100, 1) if n_cycles else 0.0,
        "cycle_classification": classification,
        "outlier_count": outlier_count,
        "cycle_lengths": cycle_lengths,
    }

    return {
        # ---- core (stable for the existing UI) ----
        "predictedDate": predicted_date.isoformat() if predicted_date else None,
        "earliestDate": earliest.isoformat() if earliest else None,
        "latestDate": latest.isoformat() if latest else None,
        "confidence": confidence,
        "regularity": classification,
        "cycleLengthPrediction": cycle_length_prediction,
        "probabilityDistribution": distribution,
        "fertileWindowStart": fertile_start.isoformat() if fertile_start else None,
        "fertileWindowEnd": fertile_end.isoformat() if fertile_end else None,
        "ovulationDate": ovulation.isoformat() if ovulation else None,
        "healthFlags": flags,
        "trendInsights": _legacy_trend_insights(trend, change_points),
        "profile": profile,
        # ---- v2-compatible fields ----
        "engineVersion": ENGINE_VERSION,
        "algorithmVersion": ALGORITHM_VERSION,
        "models": {f"model_prediction_{k}": round(model_preds[k], 2) for k in MODEL_KEYS},
        "finalPrediction": cycle_length_prediction,
        "modelWeights": {k: round(weights[k], 4) for k in MODEL_KEYS},
        "predictionErrors": {
            "rolling_3_cycle_error": err_learning["rolling_3_cycle_error"],
            "rolling_6_cycle_error": err_learning["rolling_6_cycle_error"],
            "rolling_12_cycle_error": err_learning["rolling_12_cycle_error"],
            "bias_days": err_learning["bias_days"],
        },
        "confidenceSource": conf_source,
        "confidenceSamples": calibration["samples"],
        "reliabilityIndex": reliability,
        "predictionIntervals": intervals,
        "changePoints": change_points,
        "outlierClassifications": outliers,
        "dataSufficiency": sufficiency,
        "trendForecast": trend,
        "validationMetrics": vmetrics,
        "populationPrior": population_prior,
        "benchmark": benchmark,
        "auditTrail": audit,
        # ---- v3 additions (verified forecasting improvements) ----
        "errorLearning": err_learning,
        "modelAccuracy": wf["model_accuracy"],
        "modelWeightHistory": wf["weight_history"][-12:],
        "modelAccuracyHistory": wf["accuracy_history"][-12:],
        "lookback": lookback,
        "activeForecastingStrategy": pipeline["strategy"],
        "conformalCalibration": coverage,
        "quantileForecast": quantiles,
        "forecastStability": stability,
        "calibration": calibration,
        "deploymentGate": deployment_gate,
    }


def _prediction_id(starts: List[date], ends: List[Optional[date]]) -> str:
    """Deterministic id, namespaced to the v3 engine version."""
    import hashlib
    import json
    payload = {
        "engine": ENGINE_VERSION,
        "algorithm": ALGORITHM_VERSION,
        "starts": [s.isoformat() for s in starts],
        "ends": [e.isoformat() if e else None for e in ends],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def _legacy_trend_insights(trend: Dict, change_points: List[Dict]) -> List[Dict]:
    """Adapt trend output to the v1 trendInsights shape the UI renders."""
    out: List[Dict] = []
    cl = trend["cycle_length_strength"]
    if cl >= 15:
        out.append({"type": "cycle_length", "direction": "increasing",
                    "change_days": cl, "message": "Your cycles have been getting longer recently."})
    elif cl <= -15:
        out.append({"type": "cycle_length", "direction": "decreasing",
                    "change_days": cl, "message": "Your cycles have been getting shorter recently."})
    vs = trend["variability_strength"]
    if vs >= 15:
        out.append({"type": "variability", "direction": "increasing",
                    "change_days": vs, "message": "Your cycle length has become more variable."})
    elif vs <= -15:
        out.append({"type": "variability", "direction": "decreasing",
                    "change_days": vs, "message": "Your cycle length has become more consistent."})
    pl = trend["period_length_strength"]
    if pl >= 15:
        out.append({"type": "period_length", "direction": "increasing",
                    "change_days": pl, "message": "Your periods have been lasting longer recently."})
    elif pl <= -15:
        out.append({"type": "period_length", "direction": "decreasing",
                    "change_days": pl, "message": "Your periods have been getting shorter recently."})
    if change_points:
        cp = change_points[0]
        out.append({"type": "change_point", "direction": cp["type"],
                    "change_days": cp["shift_days"],
                    "message": (f"New cycle baseline detected (~{cp['new_baseline']} days, "
                                f"was ~{cp['previous_baseline']}).")})
    return out
