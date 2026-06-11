"""MAT Period Prediction Engine — v2 (medical-grade, ensemble).

A pure, deterministic, dependency-free statistical engine (NO external AI, no
randomness). The same input ALWAYS produces identical predictions. Designed to
run in well under 100ms for 10+ years of cycle history.

This v2 builds on the v1 robust primitives (median, MAD, recency weighting,
outlier detection, fertile window, probability distribution) and adds:

  P1  Ensemble of 5 models (weighted / median / bayesian / trend / error-corrected)
      with a hard 40% cap on any single model's contribution.
  P2  Walk-forward prediction-error learning (rolling 3/6/12 error + bias).
  P3  Cycle Reliability Index (0-100) with classification bands.
  P4  Evidence-based confidence calibration (historical ±2 day hit rate).
  P5  Prediction intervals P50/P75/P90/P95.
  P6  Change-point detection (structural baseline shifts).
  P7  Advanced outlier classification (short/long/missed/logging/unknown).
  P8  Robust statistical layer (median, MAD, trimmed & winsorized means, percentiles).
  P9  Population-prior blending for users with < 6 cycles.
  P10 Trend forecasting with signed strength (-100..+100).
  P11 Monthly validation metrics (MAE / RMSE / success rate / stability).
  P12 Reproducible prediction audit trail.
  P13 Versioned engine (engine + algorithm + model weights).
  P14 Benchmark records (per-prediction backtest).
  P15 Cold-start data-sufficiency levels (0-4) capping confidence.
  P16 Self-correcting weights (per-model backtest performance).
  P17 Informational (non-diagnostic) medical safety flags.
  P18 Deterministic — no randomness anywhere.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from datetime import date, datetime, timedelta
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
    detect_outliers,
    classify_regularity,
    regularity_from_std,
    variability_score,
    fertile_window,
    probability_distribution,
    prediction_window,
    health_flags,
    RECENCY_WEIGHTS,
    OLDER_WEIGHT,
    DEFAULT_CYCLE_LENGTH,
    MIN_CYCLE_LENGTH,
    MAX_CYCLE_LENGTH,
)

# ----------------------------- Versioning (P13) -----------------------------
ENGINE_VERSION = "2.0.0"
ALGORITHM_VERSION = "ensemble-v1"
MODEL_KEYS = ["weighted", "median", "bayesian", "trend", "error_corrected"]
DEFAULT_WEIGHTS: Dict[str, float] = {
    "weighted": 0.25, "median": 0.15, "bayesian": 0.20,
    "trend": 0.15, "error_corrected": 0.25,
}
MAX_MODEL_WEIGHT = 0.40

# ----------------------------- Population prior (P9) -----------------------------
POP_CYCLE_MEAN = 28.0
POP_PERIOD_MEAN = 5.0
POP_CYCLE_VARIANCE = 12.0   # ~ std 3.46 days, typical population spread
POP_PERIOD_VARIANCE = 4.0

ACCURACY_TOLERANCE_DAYS = 2   # "within ±2 days" defines a hit (P4)
BACKTEST_WINDOW = 36          # cap walk-forward steps for performance (P19)
MIN_HISTORY = 3               # min prior cycle-lengths before back-testing


# ----------------------------- Robust statistics (P8) -----------------------------
def percentile(values: List[float], p: float) -> Optional[float]:
    """Linear-interpolation percentile (p in 0..100). Deterministic."""
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    s = sorted(values)
    rank = (p / 100.0) * (len(s) - 1)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return float(s[int(rank)])
    frac = rank - lo
    return float(s[lo] + (s[hi] - s[lo]) * frac)


def trimmed_mean(values: List[float], proportion: float = 0.1) -> Optional[float]:
    """Mean after dropping the lowest/highest ``proportion`` of values each end."""
    if not values:
        return None
    s = sorted(values)
    k = int(math.floor(len(s) * proportion))
    trimmed = s[k:len(s) - k] if len(s) - 2 * k >= 1 else s
    return float(statistics.mean(trimmed))


def winsorized_mean(values: List[float], proportion: float = 0.1) -> Optional[float]:
    """Mean after clamping the lowest/highest ``proportion`` to the boundary values."""
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    k = int(math.floor(n * proportion))
    if k == 0 or n - 2 * k < 1:
        return float(statistics.mean(s))
    lo, hi = s[k], s[n - 1 - k]
    clamped = [min(max(v, lo), hi) for v in s]
    return float(statistics.mean(clamped))


def _ols_slope_intercept(ys: List[float]) -> Tuple[float, float]:
    """Ordinary-least-squares slope + intercept over indices 0..n-1."""
    n = len(ys)
    if n < 2:
        return 0.0, (float(ys[0]) if ys else 0.0)
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return 0.0, my
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
    return slope, my - slope * mx


# ----------------------------- Outlier classification (P7) -----------------------------
def classify_outliers(cycle_lengths: List[int], starts: List[date]) -> List[Dict]:
    """Classify each statistical outlier and assign a dynamic (non-zero) weight.

    Outliers are NOT discarded — each keeps a reduced weight that depends on the
    anomaly type, so genuine signal is dampened, not deleted.
    """
    flags = detect_outliers(cycle_lengths)
    med = median_value(cycle_lengths) or POP_CYCLE_MEAN
    out: List[Dict] = []
    for i, is_out in enumerate(flags):
        if not is_out:
            continue
        c = cycle_lengths[i]
        if c < 10:
            otype, wf = "Logging Error", 0.05
        elif c < 21:
            otype, wf = "Short Cycle", 0.30
        elif c > max(60, med * 1.8):
            otype, wf = "Missed Cycle", 0.10
        elif c > 35:
            otype, wf = "Long Cycle", 0.30
        else:
            otype, wf = "Unknown Anomaly", 0.50
        # The cycle length at index i is the gap that STARTS at starts[i].
        d = starts[i].isoformat() if i < len(starts) else None
        out.append({"index": i, "date": d, "length": c,
                    "type": otype, "outlier_type": otype, "weight_factor": wf})
    return out


def _weight_factors(cycle_lengths: List[int], starts: List[date]) -> List[float]:
    """Per-cycle multiplicative weight factor (1.0 normal; reduced for outliers)."""
    factors = [1.0] * len(cycle_lengths)
    for o in classify_outliers(cycle_lengths, starts):
        factors[o["index"]] = o["weight_factor"]
    return factors


def weighted_average_dynamic(cycle_lengths: List[int],
                             weight_factors: List[float]) -> Optional[float]:
    """Recency-weighted average (40/25/15/10/6 + 4% older) scaled by per-cycle factors."""
    if not cycle_lengths:
        return None
    recent_first = list(reversed(cycle_lengths))
    fac_first = list(reversed(weight_factors))
    n = len(recent_first)
    vals: List[float] = []
    wts: List[float] = []
    for i in range(min(5, n)):
        vals.append(float(recent_first[i]))
        wts.append(RECENCY_WEIGHTS[i] * fac_first[i])
    if n > 5:
        older = recent_first[5:]
        older_fac = fac_first[5:]
        fsum = sum(older_fac)
        older_avg = (sum(v * f for v, f in zip(older, older_fac)) / fsum
                     if fsum > 0 else statistics.mean(older))
        vals.append(float(older_avg))
        wts.append(OLDER_WEIGHT)
    total = sum(wts)
    if total == 0:
        return float(statistics.mean(cycle_lengths))
    return sum(v * w for v, w in zip(vals, wts)) / total


# ----------------------------- Change-point detection (P6) -----------------------------
def detect_change_points(cycle_lengths: List[int]) -> List[Dict]:
    """Detect a recent structural shift in baseline cycle length.

    Looks for the most recent trailing segment (3-6 cycles) whose mean differs
    from the earlier baseline by more than a robust threshold while itself being
    internally consistent — i.e. a genuine new baseline, not a single outlier.
    """
    n = len(cycle_lengths)
    if n < 6:
        return []
    mad = median_absolute_deviation(cycle_lengths)
    threshold = max(3.0, 1.5 * mad)
    for seg_len in range(min(6, n - 3), 2, -1):
        recent = cycle_lengths[n - seg_len:]
        earlier = cycle_lengths[:n - seg_len]
        if len(earlier) < 3:
            continue
        recent_mean = statistics.mean(recent)
        earlier_mean = statistics.mean(earlier)
        shift = recent_mean - earlier_mean
        # Recent segment must be tight (consistent new baseline).
        if abs(shift) >= threshold and std_dev(recent) <= threshold:
            return [{
                "index": n - seg_len,
                "date": None,  # filled by caller with the start date
                "previous_baseline": round(earlier_mean, 1),
                "new_baseline": round(recent_mean, 1),
                "shift_days": round(shift, 1),
                "type": "increase" if shift > 0 else "decrease",
                "segment_length": seg_len,
            }]
    return []


# ----------------------------- Individual models (P1) -----------------------------
def _bayesian_predict(cycle_lengths: List[int]) -> float:
    """Population-prior Bayesian posterior mean of next cycle length (P9)."""
    if not cycle_lengths:
        return POP_CYCLE_MEAN
    user_vals = cycle_lengths[-12:]
    user_mean = winsorized_mean(user_vals) or POP_CYCLE_MEAN
    n = len(user_vals)
    user_var = statistics.pvariance(user_vals) if n >= 2 else POP_CYCLE_VARIANCE
    user_var = max(user_var, 1.0)
    prior_precision = 1.0 / POP_CYCLE_VARIANCE
    data_precision = n / user_var
    posterior = ((POP_CYCLE_MEAN * prior_precision + user_mean * data_precision)
                 / (prior_precision + data_precision))
    return posterior


def _trend_predict(cycle_lengths: List[int]) -> float:
    """Trend-corrected projection of the next cycle length via OLS (P10)."""
    if not cycle_lengths:
        return POP_CYCLE_MEAN
    recent = cycle_lengths[-12:]
    slope, intercept = _ols_slope_intercept([float(x) for x in recent])
    return intercept + slope * len(recent)  # project next index


def _model_predictions(cycle_lengths: List[int], weight_factors: List[float],
                       bias: float) -> Dict[str, float]:
    """Compute all five model predictions for the next cycle length."""
    if not cycle_lengths:
        base = POP_CYCLE_MEAN
        return {k: base for k in MODEL_KEYS}
    recent = cycle_lengths[-12:]
    m_weighted = weighted_average_dynamic(cycle_lengths, weight_factors) or POP_CYCLE_MEAN
    return {
        "weighted": m_weighted,
        "median": float(median_value(recent)),
        "bayesian": _bayesian_predict(cycle_lengths),
        "trend": _trend_predict(cycle_lengths),
        "error_corrected": m_weighted + bias,
    }


def _cap_weights(weights: Dict[str, float], cap: float = MAX_MODEL_WEIGHT) -> Dict[str, float]:
    """Normalise weights to sum 1 with no single weight exceeding ``cap`` (P1)."""
    w = {k: max(0.0, v) for k, v in weights.items()}
    for _ in range(12):
        total = sum(w.values())
        if total <= 0:
            return {k: 1.0 / len(w) for k in w}
        w = {k: v / total for k, v in w.items()}
        over = [k for k, v in w.items() if v > cap + 1e-9]
        if not over:
            break
        remaining = 1.0 - cap * len(over)
        others = [k for k in w if k not in over]
        others_sum = sum(w[k] for k in others)
        new_w = {}
        for k in w:
            if k in over:
                new_w[k] = cap
            elif others_sum > 0:
                new_w[k] = w[k] / others_sum * remaining
            else:
                new_w[k] = remaining / len(others) if others else cap
        w = new_w
    return w


def _ensemble_point(cycle_lengths: List[int], starts: List[date],
                    weights: Dict[str, float], bias: float) -> Tuple[float, Dict[str, float]]:
    """Combine the five models into a single prediction using ``weights``."""
    wf = _weight_factors(cycle_lengths, starts)
    preds = _model_predictions(cycle_lengths, wf, bias)
    final = sum(weights[k] * preds[k] for k in MODEL_KEYS)
    return final, preds


# ----------------------------- Walk-forward back-test (P2/P11/P14/P16) -----------------------------
def backtest(cycle_lengths: List[int], starts: List[date]) -> Dict:
    """Walk-forward back-test producing per-model errors, ensemble errors and records.

    For each cycle from MIN_HISTORY onward (capped to the most recent
    BACKTEST_WINDOW), predict it from only the earlier cycles and record the
    signed error (actual - predicted). Deterministic and O(n·window).
    """
    n = len(cycle_lengths)
    per_model: Dict[str, List[float]] = {k: [] for k in MODEL_KEYS}
    ensemble_errors: List[float] = []
    records: List[Dict] = []

    start_i = max(MIN_HISTORY, n - BACKTEST_WINDOW)
    for i in range(start_i, n):
        hist = cycle_lengths[:i]
        hist_starts = starts[:i]
        if len(hist) < MIN_HISTORY:
            continue
        wf = _weight_factors(hist, hist_starts)
        preds = _model_predictions(hist, wf, 0.0)  # no bias inside back-test
        actual = cycle_lengths[i]
        for k in MODEL_KEYS:
            per_model[k].append(abs(actual - preds[k]))
        ens = sum(DEFAULT_WEIGHTS[k] * preds[k] for k in MODEL_KEYS)
        err = actual - ens
        ensemble_errors.append(err)
        # predicted vs actual period-start dates for the benchmark record
        predicted_start = starts[i - 1] + timedelta(days=int(round(ens)))
        actual_start = starts[i]
        records.append({
            "predicted_period_start": predicted_start.isoformat(),
            "actual_period_start": actual_start.isoformat(),
            "prediction_error_days": int(round(actual_start.toordinal()
                                               - predicted_start.toordinal())),
            "model_version": ENGINE_VERSION,
        })
    return {"per_model": per_model, "ensemble_errors": ensemble_errors,
            "records": records}


def _adaptive_weights(per_model: Dict[str, List[float]]) -> Dict[str, float]:
    """Self-correcting model weights from inverse back-test MAE, capped at 40% (P16)."""
    if not per_model or not any(per_model.values()):
        return dict(DEFAULT_WEIGHTS)
    raw = {}
    for k in MODEL_KEYS:
        errs = per_model.get(k, [])
        mae = statistics.mean(errs) if errs else 5.0
        raw[k] = 1.0 / (mae + 0.5)
    return _cap_weights(raw)


def rolling_error(errors: List[float], k: int) -> Optional[float]:
    """Mean absolute ensemble error over the last ``k`` back-test predictions (P2)."""
    if not errors:
        return None
    window = errors[-k:]
    return round(statistics.mean([abs(e) for e in window]), 2)


def adaptive_bias(errors: List[float]) -> float:
    """Median signed error over the last 12 predictions — the historical bias (P2)."""
    if not errors:
        return 0.0
    return float(statistics.median(errors[-12:]))


# ----------------------------- Confidence calibration (P4) -----------------------------
def calibrated_confidence(ensemble_errors: List[float]) -> Tuple[Optional[float], str, int]:
    """Evidence-based confidence = historical ±2-day hit rate over recent cycles.

    Returns (confidence_pct_or_None, source, sample_size).
    """
    window = ensemble_errors[-12:]
    if len(window) >= 3:
        hits = sum(1 for e in window if abs(e) <= ACCURACY_TOLERANCE_DAYS)
        return round(hits / len(window) * 100, 1), "historical_accuracy", len(window)
    return None, "prior_based", len(window)


# ----------------------------- Data sufficiency / cold start (P15) -----------------------------
def data_sufficiency(n_cycles: int) -> Dict:
    """Cold-start level (0-4) that caps how confident a prediction may be."""
    if n_cycles <= 0:
        return {"level": 0, "label": "No prediction", "max_confidence": 0}
    if n_cycles == 1:
        return {"level": 1, "label": "Very low confidence", "max_confidence": 30}
    if n_cycles == 2:
        return {"level": 2, "label": "Low confidence", "max_confidence": 50}
    if n_cycles <= 5:
        return {"level": 3, "label": "Medium confidence", "max_confidence": 75}
    return {"level": 4, "label": "High confidence", "max_confidence": 95}


# ----------------------------- Reliability index (P3) -----------------------------
def reliability_index(n_cycles: int, cstd: float, accuracy_rate: Optional[float],
                      outlier_count: int, n_lengths: int,
                      missing_rate: float) -> Dict:
    """0-100 Cycle Reliability Index from five weighted factors."""
    f_cycles = clamp(n_cycles / 12.0, 0, 1)
    f_var = 1.0 - clamp(cstd / 8.0, 0, 1)
    f_acc = (accuracy_rate / 100.0) if accuracy_rate is not None else 0.5
    f_outlier = 1.0 - (clamp(outlier_count / n_lengths, 0, 1) if n_lengths else 0.0)
    f_missing = 1.0 - clamp(missing_rate, 0, 1)
    score = round(100 * (0.25 * f_cycles + 0.20 * f_var + 0.25 * f_acc
                         + 0.15 * f_outlier + 0.15 * f_missing))
    if score >= 90:
        cls = "Excellent"
    elif score >= 75:
        cls = "High"
    elif score >= 60:
        cls = "Moderate"
    elif score >= 40:
        cls = "Low"
    else:
        cls = "Very Low"
    return {
        "score": score, "classification": cls,
        "factors": {
            "number_of_cycles": round(f_cycles, 3),
            "cycle_variability": round(f_var, 3),
            "prediction_accuracy": round(f_acc, 3),
            "outlier_frequency": round(f_outlier, 3),
            "missing_data_frequency": round(f_missing, 3),
        },
    }


# ----------------------------- Prediction intervals (P5) -----------------------------
_Z = {50: 0.674, 75: 1.150, 90: 1.645, 95: 1.960}


def prediction_intervals(center: date, ensemble_errors: List[float],
                         cstd: float) -> Dict:
    """P50/P75/P90/P95 intervals from the empirical error distribution (else std-based)."""
    abs_err = [abs(e) for e in ensemble_errors]
    use_empirical = len(abs_err) >= 5
    out: Dict[str, Dict] = {}
    for level in (50, 75, 90, 95):
        if use_empirical:
            hw = percentile(abs_err, level) or 0.0
        else:
            base = cstd if cstd and cstd > 0 else 2.0
            hw = _Z[level] * base
        half = int(round(hw))
        out[f"p{level}"] = {
            "start": (center - timedelta(days=half)).isoformat(),
            "end": (center + timedelta(days=half)).isoformat(),
            "half_width_days": half,
        }
    out["source"] = "empirical_error" if use_empirical else "model_variance"
    return out


# ----------------------------- Trend forecasting (P10) -----------------------------
def trend_forecast(cycle_lengths: List[int], period_lengths: List[int]) -> Dict:
    """Signed trend strengths (-100..+100) for cycle length, variability and period."""
    def slope_strength(series: List[float], scale: float) -> float:
        if len(series) < 4:
            return 0.0
        slope, _ = _ols_slope_intercept(series[-12:])
        return round(clamp(slope * scale, -100, 100), 1)

    cl_strength = slope_strength([float(x) for x in cycle_lengths], 25.0)
    pl_strength = slope_strength([float(x) for x in period_lengths], 40.0)

    var_strength = 0.0
    if len(cycle_lengths) >= 6:
        mid = len(cycle_lengths) // 2
        older_sd = std_dev(cycle_lengths[:mid])
        recent_sd = std_dev(cycle_lengths[mid:])
        var_strength = round(clamp((recent_sd - older_sd) * 20, -100, 100), 1)

    def describe(strength: float, up: str, down: str) -> Optional[str]:
        if strength >= 15:
            return up
        if strength <= -15:
            return down
        return None

    messages = [m for m in [
        describe(cl_strength, "Your cycles are trending longer.",
                 "Your cycles are trending shorter."),
        describe(var_strength, "Your cycles are becoming more variable.",
                 "Your cycles are becoming more consistent."),
        describe(pl_strength, "Your periods are trending longer.",
                 "Your periods are trending shorter."),
    ] if m]

    return {
        "cycle_length_strength": cl_strength,
        "variability_strength": var_strength,
        "period_length_strength": pl_strength,
        "messages": messages,
    }


# ----------------------------- Validation metrics (P11) -----------------------------
def validation_metrics(ensemble_errors: List[float]) -> Dict:
    """MAE / RMSE / success rate / stability from back-test errors."""
    if not ensemble_errors:
        return {"mae": None, "rmse": None, "success_rate": None,
                "stability_score": None, "samples": 0}
    abs_err = [abs(e) for e in ensemble_errors]
    mae = statistics.mean(abs_err)
    rmse = math.sqrt(statistics.mean([e * e for e in ensemble_errors]))
    success = sum(1 for e in abs_err if e <= ACCURACY_TOLERANCE_DAYS) / len(abs_err)
    err_sd = std_dev(ensemble_errors)
    stability = clamp(100 - err_sd * 15, 0, 100)
    return {
        "mae": round(mae, 2),
        "rmse": round(rmse, 2),
        "success_rate": round(success * 100, 1),
        "stability_score": round(stability, 1),
        "samples": len(ensemble_errors),
    }


# ----------------------------- Medical safety (P17) -----------------------------
def medical_flags(cycle_lengths: List[int], period_lengths: List[int],
                  median_cycle: Optional[float], trend: Dict) -> List[Dict]:
    """Informational (non-diagnostic) flags + an 'increasing irregularity' flag."""
    flags = list(health_flags(cycle_lengths, period_lengths, median_cycle))
    if trend.get("variability_strength", 0) >= 40:
        flags.append({
            "code": "increasing_irregularity", "severity": "info",
            "message": "Your cycle length has been getting more irregular recently.",
            "value": trend["variability_strength"],
        })
    for f in flags:
        f.setdefault("guidance",
                     "Educational information only — track the pattern and consider "
                     "discussing it with a clinician if it persists.")
    return flags


# ----------------------------- Audit trail (P12) -----------------------------
def _prediction_id(starts: List[date], ends: List[Optional[date]]) -> str:
    """Deterministic id: a hash of the (versioned) input so it's reproducible."""
    payload = {
        "engine": ENGINE_VERSION,
        "algorithm": ALGORITHM_VERSION,
        "starts": [s.isoformat() for s in starts],
        "ends": [e.isoformat() if e else None for e in ends],
    }
    blob = json.dumps(payload, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


# ----------------------------- Top-level engine -----------------------------
def predict(cycles: List[Dict], today: Optional[date] = None,
            generated_at: Optional[str] = None) -> Dict:
    """Run the full v2 ensemble engine.

    ``cycles`` is a list of dicts with ``start_date`` (YYYY-MM-DD, required) and
    optional ``end_date``. ``generated_at`` is metadata only and never affects
    any prediction value (determinism, P18).
    """
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

    # ---- Back-test driven learning (P2/P11/P14/P16) ----
    bt = backtest(cycle_lengths, starts)
    weights = _adaptive_weights(bt["per_model"])
    bias = adaptive_bias(bt["ensemble_errors"])
    roll3 = rolling_error(bt["ensemble_errors"], 3)
    roll6 = rolling_error(bt["ensemble_errors"], 6)
    roll12 = rolling_error(bt["ensemble_errors"], 12)

    # ---- Ensemble prediction (P1) ----
    final_len_raw, model_preds = _ensemble_point(cycle_lengths, starts, weights, bias)
    if n_lengths == 0:
        final_len_raw = POP_CYCLE_MEAN
    final_len = clamp(final_len_raw, MIN_CYCLE_LENGTH, MAX_CYCLE_LENGTH)
    cycle_length_prediction = int(round(final_len))

    last_start = starts[-1] if starts else None
    predicted_date = (last_start + timedelta(days=cycle_length_prediction)
                      if last_start and sufficiency["level"] >= 1 else None)

    # ---- Confidence calibration capped by data sufficiency (P4/P15) ----
    conf_val, conf_source, conf_samples = calibrated_confidence(bt["ensemble_errors"])
    if conf_val is None:
        # Evidence-poor: a conservative prior-based estimate scaled by spread.
        conf_val = clamp(40 - cstd * 4, 10, sufficiency["max_confidence"])
    confidence = round(min(conf_val, sufficiency["max_confidence"]), 1)

    # ---- Outlier classification (P7) ----
    outliers = classify_outliers(cycle_lengths, starts)
    outlier_count = len(outliers)

    # ---- Reliability index (P3) ----
    accuracy_rate = (validation_metrics(bt["ensemble_errors"]).get("success_rate")
                     if bt["ensemble_errors"] else None)
    missing_rate = (1 - (len(period_lengths) / n_cycles)) if n_cycles else 1.0
    reliability = reliability_index(n_cycles, cstd, accuracy_rate,
                                    outlier_count, n_lengths, missing_rate)

    # ---- Change points (P6) ----
    change_points = detect_change_points(cycle_lengths)
    for cp in change_points:
        idx = cp["index"]
        cp["date"] = starts[idx].isoformat() if idx < len(starts) else None

    # ---- Trend forecasting (P10) ----
    trend = trend_forecast(cycle_lengths, period_lengths)

    # ---- Windows, intervals, distribution, fertile window (P5) ----
    if predicted_date is not None:
        earliest, latest, margin = prediction_window(predicted_date, cstd, int(confidence))
        distribution = probability_distribution(predicted_date, cstd, margin, int(confidence))
        intervals = prediction_intervals(predicted_date, bt["ensemble_errors"], cstd)
        fertile_start, fertile_end, ovulation = fertile_window(predicted_date)
    else:
        earliest = latest = None
        distribution = []
        intervals = {}
        fertile_start = fertile_end = ovulation = None

    # ---- Medical safety (P17) ----
    flags = medical_flags(cycle_lengths, period_lengths, med, trend)

    # ---- Validation + benchmark (P11/P14) ----
    vmetrics = validation_metrics(bt["ensemble_errors"])
    benchmark = {
        "engine_version": ENGINE_VERSION,
        "overall_accuracy": vmetrics["success_rate"],
        "mae": vmetrics["mae"],
        "rmse": vmetrics["rmse"],
        "samples": vmetrics["samples"],
        "by_regularity": classification,
        "by_cycle_count": n_cycles,
        "records": bt["records"],
    }

    # ---- Population prior (P9) ----
    blend_weight = round(clamp(n_cycles / 6.0, 0, 1), 3)
    population_prior = {
        "average_cycle_length": POP_CYCLE_MEAN,
        "average_period_length": POP_PERIOD_MEAN,
        "variance": POP_CYCLE_VARIANCE,
        "blend_weight": blend_weight,
    }

    # ---- Audit trail (P12) ----
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
            "applied_bias_days": round(bias, 2),
        },
        "confidence_source": conf_source,
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
        # ---- core (kept stable for the existing UI) ----
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
        # ---- v2 additions ----
        "engineVersion": ENGINE_VERSION,
        "algorithmVersion": ALGORITHM_VERSION,
        "models": {f"model_prediction_{k}": round(model_preds[k], 2) for k in MODEL_KEYS},
        "finalPrediction": cycle_length_prediction,
        "modelWeights": {k: round(weights[k], 4) for k in MODEL_KEYS},
        "predictionErrors": {
            "rolling_3_cycle_error": roll3,
            "rolling_6_cycle_error": roll6,
            "rolling_12_cycle_error": roll12,
            "bias_days": round(bias, 2),
        },
        "confidenceSource": conf_source,
        "confidenceSamples": conf_samples,
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
    }


def _legacy_trend_insights(trend: Dict, change_points: List[Dict]) -> List[Dict]:
    """Adapt v2 trend output to the v1 trendInsights shape the UI already renders."""
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
