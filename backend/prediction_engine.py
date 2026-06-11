"""MAT — Medical-grade menstrual cycle prediction engine.

A pure, deterministic, dependency-free statistical engine (no external AI). The
same input ALWAYS produces the same output. Designed to run in well under 100ms
for 10+ years of cycle history.

Design highlights
-----------------
* Weighted prediction — recent cycles dominate (40/25/15/10/6/4), NOT a flat mean.
* Robust outlier handling — Median Absolute Deviation (MAD); outliers keep only
  10% of their weight (reduced by 90%).
* Adaptive self-correction — walk-forward back-testing measures the engine's own
  historical prediction error and applies a bias correction to future predictions.
* Uncertainty modelling — every prediction returns a window (earliest/latest) and
  a per-day probability distribution, never a single bare date.
* Confidence scoring (0-100) — blends cycle count, variability, historical
  accuracy and data quality.
* Cycle classification, trend detection and informational (non-diagnostic) health
  flags.

Everything in this module is a pure function of its inputs so it is trivially and
exhaustively unit-testable.
"""
from __future__ import annotations

import math
import statistics
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

# ----------------------------- Constants -----------------------------
# Most-recent-first weights for the weighted prediction. Index 0 == most recent.
RECENCY_WEIGHTS: List[float] = [0.40, 0.25, 0.15, 0.10, 0.06]
OLDER_WEIGHT: float = 0.04          # all cycles older than the 5th share this
OUTLIER_WEIGHT_FACTOR: float = 0.10  # outliers keep 10% of their weight (-90%)
# Clinically meaningful absolute floor (days) used only when MAD degenerates to 0
# (i.e. nearly all cycles are identical) so trivial 1-3 day variation is never
# flagged, but a genuine extreme (e.g. a missed period) still is.
OUTLIER_ABS_FLOOR: float = 10.0
# Consistency constant converting mean-absolute-deviation -> MAD-equivalent scale
# (MAD ≈ 0.8453 * MeanAD for normally distributed data).
_MEANAD_TO_MAD: float = 0.8453

DEFAULT_CYCLE_LENGTH: int = 28
DEFAULT_PERIOD_LENGTH: int = 5

# Plausible physiological clamps for a predicted cycle length.
MIN_CYCLE_LENGTH: int = 15
MAX_CYCLE_LENGTH: int = 60

# Probability distribution window (days relative to the predicted day).
PROB_WINDOW_START: int = -7
PROB_WINDOW_END: int = 6  # inclusive -> 14 days total

# Classification thresholds on cycle-length standard deviation (days).
CLASS_VERY_REGULAR = 2.0
CLASS_REGULAR = 4.0
CLASS_MODERATE = 7.0


# ----------------------------- Small helpers -----------------------------
def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def coerce_date(value) -> Optional[date]:
    """Parse a YYYY-MM-DD string / date / datetime into a date (or None)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
    return None


# ----------------------------- Core calculations -----------------------------
def period_length(start: date, end: date) -> int:
    """Inclusive period length in days: end - start + 1."""
    return (end - start).days + 1


def cycle_lengths_from_starts(starts: List[date]) -> List[int]:
    """Days between consecutive period-start dates (oldest -> newest)."""
    s = sorted(starts)
    return [(s[i + 1] - s[i]).days for i in range(len(s) - 1)]


def median_value(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return float(statistics.median(values))


def mean_value(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return float(statistics.mean(values))


def std_dev(values: List[float]) -> float:
    """Population standard deviation; 0.0 for <2 samples."""
    if len(values) < 2:
        return 0.0
    return float(statistics.pstdev(values))


def median_absolute_deviation(values: List[float]) -> float:
    """MAD = median(|x_i - median(x)|)."""
    if not values:
        return 0.0
    m = statistics.median(values)
    return float(statistics.median([abs(v - m) for v in values]))


def detect_outliers(cycle_lengths: List[int]) -> List[bool]:
    """Flag a cycle as an outlier when |len - median| > 3 * MAD.

    Returns a bool list aligned (oldest -> newest) with ``cycle_lengths``. With
    fewer than 3 cycles, or when MAD == 0 (identical cycles), nothing is flagged.
    """
    n = len(cycle_lengths)
    if n < 3:
        return [False] * n
    m = statistics.median(cycle_lengths)
    mad = median_absolute_deviation(cycle_lengths)
    if mad == 0:
        # Degenerate spread: most cycles are identical so MAD collapses to 0 and
        # the primary 3*MAD rule can't see a genuine extreme (e.g. a missed
        # period). Fall back to a robust mean-absolute-deviation scale, with an
        # absolute floor so clinically trivial 1-3 day variation is never
        # flagged. If every cycle is identical (MeanAD == 0) there are no outliers.
        mean_ad = statistics.mean([abs(c - m) for c in cycle_lengths])
        if mean_ad == 0:
            return [False] * n
        threshold = max(3 * _MEANAD_TO_MAD * mean_ad, OUTLIER_ABS_FLOOR)
        return [abs(c - m) > threshold for c in cycle_lengths]
    threshold = 3 * mad
    return [abs(c - m) > threshold for c in cycle_lengths]


def weighted_average(cycle_lengths: List[int],
                     outliers: Optional[List[bool]] = None) -> Optional[float]:
    """Recency-weighted average of cycle lengths (oldest -> newest input).

    The 5 most recent cycles get 40/25/15/10/6% weight; everything older shares
    the remaining 4%. Outliers keep only 10% of their assigned weight. Weights
    are normalised so the result is a true weighted mean for any history length.
    """
    if not cycle_lengths:
        return None
    if outliers is None:
        outliers = [False] * len(cycle_lengths)

    recent_first = list(reversed(cycle_lengths))
    out_first = list(reversed(outliers))
    n = len(recent_first)

    values: List[float] = []
    weights: List[float] = []

    for i in range(min(5, n)):
        w = RECENCY_WEIGHTS[i]
        if out_first[i]:
            w *= OUTLIER_WEIGHT_FACTOR
        values.append(float(recent_first[i]))
        weights.append(w)

    if n > 5:
        older = recent_first[5:]
        older_out = out_first[5:]
        ow = [OUTLIER_WEIGHT_FACTOR if o else 1.0 for o in older_out]
        older_avg = sum(v * w for v, w in zip(older, ow)) / sum(ow)
        values.append(float(older_avg))
        weights.append(OLDER_WEIGHT)

    total = sum(weights)
    if total == 0:  # every considered cycle was an outlier with zero residual weight
        return float(mean_value(cycle_lengths))
    return sum(v * w for v, w in zip(values, weights)) / total


def weighted_prediction(cycle_lengths: List[int]) -> Optional[float]:
    """Convenience: outlier-aware weighted prediction of the next cycle length."""
    if not cycle_lengths:
        return None
    return weighted_average(cycle_lengths, detect_outliers(cycle_lengths))


# ----------------------------- Adaptive learning -----------------------------
def backtest_errors(cycle_lengths: List[int], min_history: int = 3) -> List[float]:
    """Walk-forward back-test: for each cycle from ``min_history`` onward, predict
    it using only earlier cycles and record (actual - predicted).

    These errors quantify how well the engine has predicted *this* user, and are
    used both for the accuracy score and for the adaptive bias correction.
    """
    errors: List[float] = []
    for i in range(min_history, len(cycle_lengths)):
        history = cycle_lengths[:i]
        pred = weighted_average(history, detect_outliers(history))
        if pred is None:
            continue
        errors.append(cycle_lengths[i] - pred)
    return errors


def accuracy_from_errors(errors: List[float]) -> Optional[float]:
    """Prediction accuracy 0-100 from back-test errors (lower MAE -> higher)."""
    if not errors:
        return None
    mae = statistics.mean([abs(e) for e in errors])
    return round(clamp(100 - mae * 12, 0, 100), 1)


def adaptive_bias(errors: List[float]) -> float:
    """Median back-test error used to self-correct the next prediction.

    A positive bias means the engine has historically under-predicted cycle
    length, so future predictions are nudged longer (and vice-versa).
    """
    if not errors:
        return 0.0
    return float(statistics.median(errors))


# ----------------------------- Confidence -----------------------------
def confidence_score(n_cycles: int, cycle_std: float,
                     accuracy: Optional[float], data_quality: float) -> int:
    """Blend four factors into a 0-100 confidence score.

    Components: cycle count (0-40), variability (0-30), historical accuracy
    (0-20) and data quality (0-10).
    """
    # Cycle count: 1 -> low, 6 -> medium, 12+ -> high.
    if n_cycles >= 12:
        count_c = 40.0
    elif n_cycles >= 6:
        count_c = 25.0 + (n_cycles - 6) / 6.0 * 15.0
    elif n_cycles >= 1:
        count_c = n_cycles / 6.0 * 25.0
    else:
        count_c = 0.0

    # Variability: std 0 -> full marks, std >= 8 -> none.
    if n_cycles >= 2:
        var_c = clamp(30.0 * (1 - clamp(cycle_std, 0, 8) / 8.0), 0, 30)
    else:
        var_c = 0.0

    # Historical accuracy (neutral 10/20 when not yet measurable).
    acc_c = (accuracy / 100.0 * 20.0) if accuracy is not None else 10.0

    # Data quality.
    dq_c = clamp(data_quality, 0, 100) / 100.0 * 10.0

    return int(round(clamp(count_c + var_c + acc_c + dq_c, 0, 100)))


def data_quality_score(n_cycles: int, period_lengths: List[int],
                       cycle_lengths: List[int]) -> float:
    """0-100 data-quality estimate from history depth + logging completeness."""
    if n_cycles == 0:
        return 0.0
    depth = clamp(n_cycles / 6.0, 0, 1)  # 6+ cycles == full depth credit
    # Completeness: fraction of cycles with a logged period end_date.
    completeness = clamp(len(period_lengths) / n_cycles, 0, 1)
    return round((0.5 * depth + 0.5 * completeness) * 100, 1)


def regularity_from_std(cycle_std: float) -> int:
    """0-100 regularity score (higher == more regular)."""
    return int(round(clamp(100 - cycle_std * 12, 0, 100)))


def variability_score(cycle_std: float) -> float:
    """0-100 variability score (higher == more variable)."""
    return round(clamp(cycle_std * 12, 0, 100), 1)


# ----------------------------- Classification -----------------------------
def classify_regularity(n_cycles: int, cycle_std: float) -> str:
    """Classify cycle regularity from the standard deviation of cycle lengths."""
    if n_cycles < 3:
        return "Unknown"
    if cycle_std < CLASS_VERY_REGULAR:
        return "Very Regular"
    if cycle_std < CLASS_REGULAR:
        return "Regular"
    if cycle_std <= CLASS_MODERATE:
        return "Moderately Irregular"
    return "Highly Irregular"


# ----------------------------- Prediction window -----------------------------
def prediction_window(predicted: date, cycle_std: float,
                      confidence: int) -> Tuple[date, date, int]:
    """Symmetric uncertainty window around the predicted date.

    Width scales with variability and *widens* when confidence is low.
    """
    base = cycle_std if cycle_std and cycle_std > 0 else 2.0
    conf_factor = 1.0 + (100 - confidence) / 100.0
    margin = int(max(1, round(base * conf_factor)))
    return predicted - timedelta(days=margin), predicted + timedelta(days=margin), margin


# ----------------------------- Probability distribution -----------------------------
def probability_distribution(predicted: date, cycle_std: float, margin: int,
                             confidence: int) -> List[Dict]:
    """Per-day likelihood (0-100) that the period starts on each day of a 14-day
    window centred on the predicted date. A Gaussian peaks on the predicted day.
    """
    sigma = max(1.0, cycle_std if cycle_std and cycle_std > 0 else float(margin or 2))
    peak = clamp(confidence, 40, 95)
    out: List[Dict] = []
    for offset in range(PROB_WINDOW_START, PROB_WINDOW_END + 1):
        prob = peak * math.exp(-(offset ** 2) / (2 * sigma ** 2))
        out.append({
            "date": (predicted + timedelta(days=offset)).isoformat(),
            "dayOffset": offset,
            "probability": int(round(prob)),
        })
    return out


# ----------------------------- Trend detection -----------------------------
def _half_means(series: List[float]) -> Tuple[float, float]:
    mid = len(series) // 2
    return statistics.mean(series[:mid]), statistics.mean(series[mid:])


def detect_trends(cycle_lengths: List[int], period_lengths: List[int]) -> List[Dict]:
    """Detect lengthening/shortening cycles & periods and variability shifts."""
    trends: List[Dict] = []

    if len(cycle_lengths) >= 4:
        older_m, recent_m = _half_means([float(x) for x in cycle_lengths])
        diff = recent_m - older_m
        if diff >= 1.5:
            trends.append({"type": "cycle_length", "direction": "increasing",
                           "change_days": round(diff, 1),
                           "message": "Your cycles have been getting longer recently."})
        elif diff <= -1.5:
            trends.append({"type": "cycle_length", "direction": "decreasing",
                           "change_days": round(diff, 1),
                           "message": "Your cycles have been getting shorter recently."})

        mid = len(cycle_lengths) // 2
        older_sd = std_dev(cycle_lengths[:mid])
        recent_sd = std_dev(cycle_lengths[mid:])
        var_diff = recent_sd - older_sd
        if var_diff >= 1.0:
            trends.append({"type": "variability", "direction": "increasing",
                           "change_days": round(var_diff, 1),
                           "message": "Your cycle length has become more variable."})
        elif var_diff <= -1.0:
            trends.append({"type": "variability", "direction": "decreasing",
                           "change_days": round(var_diff, 1),
                           "message": "Your cycle length has become more consistent."})

    if len(period_lengths) >= 4:
        older_m, recent_m = _half_means([float(x) for x in period_lengths])
        diff = recent_m - older_m
        if diff >= 1.0:
            trends.append({"type": "period_length", "direction": "increasing",
                           "change_days": round(diff, 1),
                           "message": "Your periods have been lasting longer recently."})
        elif diff <= -1.0:
            trends.append({"type": "period_length", "direction": "decreasing",
                           "change_days": round(diff, 1),
                           "message": "Your periods have been getting shorter recently."})

    return trends


# ----------------------------- Health flags (informational only) -----------------------------
def health_flags(cycle_lengths: List[int], period_lengths: List[int],
                 median_cycle: Optional[float]) -> List[Dict]:
    """Generate informational (NON-diagnostic) health flags.

    These surface patterns worth noticing — they never diagnose a condition.
    """
    flags: List[Dict] = []

    def add(code: str, severity: str, message: str, value=None):
        flags.append({"code": code, "severity": severity,
                      "message": message, "value": value})

    short = [c for c in cycle_lengths if c < 21]
    long_c = [c for c in cycle_lengths if 35 < c <= 90]
    very_long = [c for c in cycle_lengths if c > 90]
    if short:
        add("short_cycle", "info",
            f"{len(short)} cycle(s) were shorter than 21 days.", min(short))
    if long_c:
        add("long_cycle", "info",
            f"{len(long_c)} cycle(s) were longer than 35 days.", max(long_c))
    if very_long:
        add("very_long_cycle", "warning",
            f"{len(very_long)} gap(s) exceeded 90 days — a possible missed period.",
            max(very_long))

    long_periods = [p for p in period_lengths if p > 10]
    if long_periods:
        add("long_period", "warning",
            f"{len(long_periods)} period(s) lasted longer than 10 days.",
            max(long_periods))

    # Sudden change > 10 days between consecutive cycles.
    sudden = 0
    biggest = 0
    for i in range(1, len(cycle_lengths)):
        change = abs(cycle_lengths[i] - cycle_lengths[i - 1])
        if change > 10:
            sudden += 1
            biggest = max(biggest, change)
    if sudden:
        add("sudden_change", "info",
            f"A cycle length changed by more than 10 days {sudden} time(s).", biggest)

    # Repeated missed periods: two or more cycles far above the personal median.
    if median_cycle:
        missed = [c for c in cycle_lengths if c > max(45, median_cycle * 1.5)]
        if len(missed) >= 2:
            add("repeated_missed", "warning",
                "Several unusually long gaps suggest repeated missed periods.",
                len(missed))

    return flags


# ----------------------------- Fertile window -----------------------------
def fertile_window(predicted_date: date) -> Tuple[date, date, date]:
    """Estimate the fertile window from the predicted next-period date.

    Ovulation is ~14 days before the next period; the fertile window spans the
    5 days before ovulation through 1 day after (sperm viability + egg lifespan).
    Returns (fertile_start, fertile_end, ovulation_date).
    """
    ovulation = predicted_date - timedelta(days=14)
    return ovulation - timedelta(days=5), ovulation + timedelta(days=1), ovulation


# ----------------------------- Top-level engine -----------------------------
def predict(cycles: List[Dict], today: Optional[date] = None) -> Dict:
    """Run the full prediction engine over a list of cycle records.

    ``cycles`` is a list of dicts with ``start_date`` (required, YYYY-MM-DD) and
    optional ``end_date``. Returns the API-shaped response plus a ``profile``.
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
    n_cycles = len(starts)
    cycle_lengths = cycle_lengths_from_starts(starts)
    period_lengths = [period_length(sd, ed) for sd, ed in parsed if ed is not None]

    med = median_value(cycle_lengths)
    cstd = std_dev(cycle_lengths)
    outliers = detect_outliers(cycle_lengths)

    raw_pred = weighted_average(cycle_lengths, outliers)
    errors = backtest_errors(cycle_lengths)
    accuracy = accuracy_from_errors(errors)
    bias = adaptive_bias(errors)

    if raw_pred is None:
        predicted_len = float(DEFAULT_CYCLE_LENGTH)
    else:
        predicted_len = clamp(raw_pred + bias, MIN_CYCLE_LENGTH, MAX_CYCLE_LENGTH)
    cycle_length_prediction = int(round(predicted_len))

    last_start = starts[-1] if starts else None
    predicted_date = (last_start + timedelta(days=cycle_length_prediction)
                      if last_start else None)

    dq = data_quality_score(n_cycles, period_lengths, cycle_lengths)
    confidence = confidence_score(n_cycles, cstd, accuracy, dq)
    classification = classify_regularity(n_cycles, cstd)

    if predicted_date is not None:
        earliest, latest, margin = prediction_window(predicted_date, cstd, confidence)
        distribution = probability_distribution(predicted_date, cstd, margin, confidence)
        fertile_start, fertile_end, ovulation = fertile_window(predicted_date)
    else:
        earliest = latest = None
        distribution = []
        fertile_start = fertile_end = ovulation = None

    trends = detect_trends(cycle_lengths, period_lengths)
    flags = health_flags(cycle_lengths, period_lengths, med)

    avg_period = mean_value(period_lengths)
    profile = {
        "cycle_count": n_cycles,
        "average_cycle_length": round(mean_value(cycle_lengths), 1) if cycle_lengths else None,
        "median_cycle_length": round(med, 1) if med is not None else None,
        "average_period_length": round(avg_period, 1) if avg_period is not None else None,
        "cycle_standard_deviation": round(cstd, 2),
        "cycle_variability_score": variability_score(cstd) if cycle_lengths else None,
        "regularity_score": regularity_from_std(cstd) if cycle_lengths else None,
        "prediction_accuracy_score": accuracy,
        "adaptive_bias_days": round(bias, 2),
        "data_quality_score": dq,
        "cycle_classification": classification,
        "outlier_count": sum(1 for o in outliers if o),
        "cycle_lengths": cycle_lengths,
    }

    return {
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
        "trendInsights": trends,
        "profile": profile,
    }
