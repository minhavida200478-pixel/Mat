"""Exhaustive unit tests for the MAT period prediction engine v2 (ensemble).

PURE unit tests — they import prediction_engine_v2 directly and never hit the
network or the database. Fast, deterministic, and target 95%+ coverage of the
v2 statistical logic across all 20 Phase-2 priority items.

Run:  cd /app/backend && python -m pytest tests/test_prediction_engine_v2.py -v
"""
from __future__ import annotations

import time
from datetime import date, timedelta

import pytest

import prediction_engine_v2 as v2


# ----------------------------- helpers -----------------------------
def starts_from_lengths(first: date, lengths):
    s = [first]
    for L in lengths:
        s.append(s[-1] + timedelta(days=L))
    return s


def cycles_from_lengths(first: date, lengths, period_len=5):
    starts = starts_from_lengths(first, lengths)
    out = []
    for s in starts:
        out.append({"start_date": s.isoformat(),
                    "end_date": (s + timedelta(days=period_len - 1)).isoformat()})
    return out


REGULAR = [28, 29, 27, 28, 30, 26, 28, 29, 27, 28, 31, 28, 27, 29]
FIRST = date(2024, 1, 1)


# ============================================================================
# P8 — Robust statistics
# ============================================================================
class TestPercentile:
    def test_empty(self):
        assert v2.percentile([], 50) is None

    def test_single(self):
        assert v2.percentile([7], 90) == 7.0

    def test_median_of_odd(self):
        assert v2.percentile([1, 2, 3], 50) == 2.0

    def test_interpolation(self):
        # 75th pct of 1..5 => rank 3.0 -> exact element 4
        assert v2.percentile([1, 2, 3, 4, 5], 75) == 4.0

    def test_fractional_interpolation(self):
        # 90th pct of 1..5 => rank 3.6 -> 4 + 0.6*(5-4) = 4.6
        assert v2.percentile([1, 2, 3, 4, 5], 90) == pytest.approx(4.6)

    def test_zero_pct(self):
        assert v2.percentile([5, 1, 3], 0) == 1.0

    def test_hundred_pct(self):
        assert v2.percentile([5, 1, 3], 100) == 5.0


class TestTrimmedMean:
    def test_empty(self):
        assert v2.trimmed_mean([]) is None

    def test_drops_extremes(self):
        # proportion 0.1 of 10 -> k=1, drop one low+high
        vals = [1, 10, 10, 10, 10, 10, 10, 10, 10, 100]
        assert v2.trimmed_mean(vals, 0.1) == 10.0

    def test_small_list_no_trim(self):
        assert v2.trimmed_mean([2, 4], 0.1) == 3.0


class TestWinsorizedMean:
    def test_empty(self):
        assert v2.winsorized_mean([]) is None

    def test_clamps_extremes(self):
        vals = [1, 10, 10, 10, 10, 10, 10, 10, 10, 100]
        # k=1: 1->10, 100->10 => all 10
        assert v2.winsorized_mean(vals, 0.1) == 10.0

    def test_no_winsor_when_k_zero(self):
        assert v2.winsorized_mean([2, 4, 6], 0.1) == 4.0


class TestOLS:
    def test_too_short(self):
        assert v2._ols_slope_intercept([5]) == (0.0, 5.0)

    def test_empty(self):
        assert v2._ols_slope_intercept([]) == (0.0, 0.0)

    def test_perfect_line(self):
        slope, intercept = v2._ols_slope_intercept([2, 4, 6, 8])
        assert slope == pytest.approx(2.0)
        assert intercept == pytest.approx(2.0)

    def test_flat_line(self):
        slope, intercept = v2._ols_slope_intercept([5, 5, 5, 5])
        assert slope == pytest.approx(0.0)
        assert intercept == pytest.approx(5.0)


# ============================================================================
# P7 — Advanced outlier classification
# ============================================================================
class TestClassifyOutliers:
    def test_logging_error(self):
        lengths = [28, 28, 28, 28, 5, 28, 28]
        starts = starts_from_lengths(FIRST, lengths)
        outs = v2.classify_outliers(lengths, starts)
        types = [o["outlier_type"] for o in outs]
        assert "Logging Error" in types
        log = next(o for o in outs if o["outlier_type"] == "Logging Error")
        assert log["weight_factor"] == 0.05
        assert log["date"] is not None

    def test_missed_cycle(self):
        lengths = [28, 28, 28, 28, 90, 28, 28]
        starts = starts_from_lengths(FIRST, lengths)
        outs = v2.classify_outliers(lengths, starts)
        assert any(o["outlier_type"] == "Missed Cycle" for o in outs)

    def test_short_cycle(self):
        lengths = [28, 28, 28, 28, 17, 28, 28]
        starts = starts_from_lengths(FIRST, lengths)
        outs = v2.classify_outliers(lengths, starts)
        assert any(o["outlier_type"] == "Short Cycle" for o in outs)

    def test_long_cycle(self):
        lengths = [28, 28, 28, 28, 40, 28, 28]
        starts = starts_from_lengths(FIRST, lengths)
        outs = v2.classify_outliers(lengths, starts)
        assert any(o["outlier_type"] == "Long Cycle" for o in outs)

    def test_no_outliers_when_regular(self):
        lengths = [28, 28, 28, 28, 28]
        starts = starts_from_lengths(FIRST, lengths)
        assert v2.classify_outliers(lengths, starts) == []


class TestWeightFactors:
    def test_outlier_reduces_factor(self):
        lengths = [28, 28, 28, 28, 5, 28, 28]
        starts = starts_from_lengths(FIRST, lengths)
        factors = v2._weight_factors(lengths, starts)
        assert factors[4] < 1.0
        assert factors[0] == 1.0


class TestWeightedAverageDynamic:
    def test_empty(self):
        assert v2.weighted_average_dynamic([], []) is None

    def test_recency_weighting(self):
        lengths = [40, 28, 28, 28, 28]  # most recent is 28
        factors = [1.0] * 5
        result = v2.weighted_average_dynamic(lengths, factors)
        assert 28 <= result < 31  # old 40 dampened by recency

    def test_long_history_older_bucket(self):
        lengths = [28] * 10
        factors = [1.0] * 10
        result = v2.weighted_average_dynamic(lengths, factors)
        assert result == pytest.approx(28.0)

    def test_all_zero_weight_fallback(self):
        lengths = [28, 30]
        factors = [0.0, 0.0]
        result = v2.weighted_average_dynamic(lengths, factors)
        assert result == pytest.approx(29.0)


# ============================================================================
# P6 — Change-point detection
# ============================================================================
class TestChangePoints:
    def test_too_few(self):
        assert v2.detect_change_points([28, 28, 28]) == []

    def test_detects_baseline_increase(self):
        lengths = [28, 28, 28, 28, 35, 35, 35, 35]
        cps = v2.detect_change_points(lengths)
        assert cps
        assert cps[0]["type"] == "increase"
        assert cps[0]["new_baseline"] > cps[0]["previous_baseline"]

    def test_detects_baseline_decrease(self):
        lengths = [35, 35, 35, 35, 28, 28, 28, 28]
        cps = v2.detect_change_points(lengths)
        assert cps
        assert cps[0]["type"] == "decrease"

    def test_no_change_when_stable(self):
        assert v2.detect_change_points([28] * 10) == []


# ============================================================================
# P1 / P9 / P10 — Individual models
# ============================================================================
class TestModels:
    def test_bayesian_empty_returns_prior(self):
        assert v2._bayesian_predict([]) == v2.POP_CYCLE_MEAN

    def test_bayesian_blends_toward_user(self):
        # Many user cycles at 32 -> posterior should move above pop mean (28)
        result = v2._bayesian_predict([32] * 12)
        assert 28 < result <= 32

    def test_trend_empty(self):
        assert v2._trend_predict([]) == v2.POP_CYCLE_MEAN

    def test_trend_projects_upward(self):
        result = v2._trend_predict([26, 27, 28, 29, 30])
        assert result > 30

    def test_model_predictions_empty(self):
        preds = v2._model_predictions([], [], 0.0)
        assert all(v == v2.POP_CYCLE_MEAN for v in preds.values())

    def test_model_predictions_keys(self):
        lengths = REGULAR
        wf = [1.0] * len(lengths)
        preds = v2._model_predictions(lengths, wf, 1.0)
        assert set(preds.keys()) == set(v2.MODEL_KEYS)
        # error_corrected = weighted + bias
        assert preds["error_corrected"] == pytest.approx(preds["weighted"] + 1.0)


# ============================================================================
# P1 — Weight capping at 40%
# ============================================================================
class TestCapWeights:
    def test_no_weight_exceeds_cap(self):
        raw = {"weighted": 10, "median": 0.1, "bayesian": 0.1,
               "trend": 0.1, "error_corrected": 0.1}
        capped = v2._cap_weights(raw)
        assert all(w <= v2.MAX_MODEL_WEIGHT + 1e-6 for w in capped.values())
        assert sum(capped.values()) == pytest.approx(1.0)

    def test_all_zero_uniform(self):
        raw = {k: 0.0 for k in v2.MODEL_KEYS}
        capped = v2._cap_weights(raw)
        assert all(w == pytest.approx(0.2) for w in capped.values())

    def test_sums_to_one(self):
        raw = {"weighted": 3, "median": 2, "bayesian": 1,
               "trend": 1, "error_corrected": 1}
        capped = v2._cap_weights(raw)
        assert sum(capped.values()) == pytest.approx(1.0)


class TestEnsemblePoint:
    def test_combines_models(self):
        lengths = REGULAR
        starts = starts_from_lengths(FIRST, [28] * (len(lengths)))
        weights = dict(v2.DEFAULT_WEIGHTS)
        final, preds = v2._ensemble_point(lengths, starts, weights, 0.0)
        assert 25 <= final <= 31
        assert set(preds.keys()) == set(v2.MODEL_KEYS)


# ============================================================================
# P2 / P11 / P14 / P16 — Backtest & learning
# ============================================================================
class TestBacktest:
    def test_produces_errors_and_records(self):
        lengths = REGULAR
        starts = starts_from_lengths(FIRST, REGULAR)[:len(lengths)]
        # align starts length with lengths (cycle_lengths has n-1 vs starts)
        starts = starts_from_lengths(FIRST, REGULAR)
        cl = v2.cycle_lengths_from_starts(starts)
        bt = v2.backtest(cl, starts)
        assert len(bt["ensemble_errors"]) >= 1
        assert len(bt["records"]) == len(bt["ensemble_errors"])
        for k in v2.MODEL_KEYS:
            assert k in bt["per_model"]
        rec = bt["records"][0]
        assert "predicted_period_start" in rec
        assert "actual_period_start" in rec
        assert rec["model_version"] == v2.ENGINE_VERSION

    def test_short_history_no_errors(self):
        starts = starts_from_lengths(FIRST, [28, 28])  # 2 cycle lengths
        cl = v2.cycle_lengths_from_starts(starts)
        bt = v2.backtest(cl, starts)
        assert bt["ensemble_errors"] == []


class TestAdaptiveWeights:
    def test_default_when_no_data(self):
        assert v2._adaptive_weights({}) == v2.DEFAULT_WEIGHTS

    def test_better_model_gets_more_weight(self):
        per_model = {"weighted": [0.5, 0.5], "median": [5, 5],
                     "bayesian": [5, 5], "trend": [5, 5],
                     "error_corrected": [5, 5]}
        w = v2._adaptive_weights(per_model)
        assert w["weighted"] == max(w.values())
        assert all(x <= v2.MAX_MODEL_WEIGHT + 1e-6 for x in w.values())


class TestRollingError:
    def test_empty(self):
        assert v2.rolling_error([], 3) is None

    def test_mean_abs(self):
        assert v2.rolling_error([-2, 2, -2], 3) == 2.0

    def test_window(self):
        assert v2.rolling_error([10, 10, 1, 1, 1], 3) == 1.0


class TestAdaptiveBias:
    def test_empty(self):
        assert v2.adaptive_bias([]) == 0.0

    def test_median_signed(self):
        assert v2.adaptive_bias([1, 2, 3]) == 2.0


# ============================================================================
# P4 — Confidence calibration
# ============================================================================
class TestCalibratedConfidence:
    def test_prior_when_too_few(self):
        conf, source, n = v2.calibrated_confidence([1.0, 2.0])
        assert conf is None
        assert source == "prior_based"
        assert n == 2

    def test_historical_hit_rate(self):
        errors = [0, 1, -1, 5, 0, 2]  # 5 within +-2 of 6 -> 83.3%
        conf, source, n = v2.calibrated_confidence(errors)
        assert source == "historical_accuracy"
        assert conf == pytest.approx(83.3, abs=0.1)


# ============================================================================
# P15 — Data sufficiency / cold start
# ============================================================================
class TestDataSufficiency:
    @pytest.mark.parametrize("n,level,maxc", [
        (0, 0, 0), (1, 1, 30), (2, 2, 50), (4, 3, 75), (6, 4, 95), (20, 4, 95),
    ])
    def test_levels(self, n, level, maxc):
        s = v2.data_sufficiency(n)
        assert s["level"] == level
        assert s["max_confidence"] == maxc


# ============================================================================
# P3 — Reliability index
# ============================================================================
class TestReliabilityIndex:
    def test_high_for_good_data(self):
        r = v2.reliability_index(12, 1.0, 95.0, 0, 12, 0.0)
        assert r["score"] >= 90
        assert r["classification"] == "Excellent"

    def test_low_for_poor_data(self):
        r = v2.reliability_index(1, 8.0, None, 3, 3, 1.0)
        assert r["score"] < 40
        assert r["classification"] == "Very Low"

    def test_factors_present(self):
        r = v2.reliability_index(6, 3.0, 70.0, 1, 6, 0.2)
        assert set(r["factors"].keys()) == {
            "number_of_cycles", "cycle_variability", "prediction_accuracy",
            "outlier_frequency", "missing_data_frequency"}

    @pytest.mark.parametrize("expected", ["Excellent", "High", "Moderate", "Low", "Very Low"])
    def test_classification_bands_reachable(self, expected):
        # sweep across configs to ensure each band is reachable
        configs = [
            (12, 0.5, 99.0, 0, 12, 0.0),
            (10, 2.0, 80.0, 0, 10, 0.05),
            (6, 4.0, 60.0, 1, 6, 0.2),
            (3, 6.0, 40.0, 1, 3, 0.4),
            (1, 8.0, 5.0, 2, 3, 0.9),
        ]
        seen = {v2.reliability_index(*c)["classification"] for c in configs}
        assert expected in seen


# ============================================================================
# P5 — Prediction intervals
# ============================================================================
class TestPredictionIntervals:
    def test_empirical_when_enough(self):
        center = date(2024, 6, 1)
        errors = [0, 1, -1, 2, -2, 3]
        iv = v2.prediction_intervals(center, errors, 2.0)
        assert iv["source"] == "empirical_error"
        for lvl in ("p50", "p75", "p90", "p95"):
            assert lvl in iv
            assert "start" in iv[lvl] and "end" in iv[lvl]

    def test_model_variance_when_few(self):
        center = date(2024, 6, 1)
        iv = v2.prediction_intervals(center, [1.0], 3.0)
        assert iv["source"] == "model_variance"

    def test_widths_monotonic(self):
        center = date(2024, 6, 1)
        iv = v2.prediction_intervals(center, [], 3.0)
        widths = [iv[f"p{l}"]["half_width_days"] for l in (50, 75, 90, 95)]
        assert widths == sorted(widths)


# ============================================================================
# P10 — Trend forecasting
# ============================================================================
class TestTrendForecast:
    def test_too_short_returns_zero(self):
        t = v2.trend_forecast([28, 29], [])
        assert t["cycle_length_strength"] == 0.0

    def test_lengthening_trend(self):
        t = v2.trend_forecast([26, 27, 28, 29, 30, 31], [5, 5, 5, 5, 5, 5])
        assert t["cycle_length_strength"] > 0
        assert any("longer" in m for m in t["messages"])

    def test_increasing_variability(self):
        lengths = [28, 28, 28, 28, 20, 36, 22, 34]
        t = v2.trend_forecast(lengths, [])
        assert "variability_strength" in t

    def test_period_trend(self):
        t = v2.trend_forecast([28] * 6, [3, 4, 5, 6, 7, 8])
        assert t["period_length_strength"] > 0


# ============================================================================
# P11 — Validation metrics
# ============================================================================
class TestValidationMetrics:
    def test_empty(self):
        m = v2.validation_metrics([])
        assert m["samples"] == 0
        assert m["mae"] is None

    def test_computes_mae_rmse(self):
        m = v2.validation_metrics([0, 0, 0, 0])
        assert m["mae"] == 0.0
        assert m["rmse"] == 0.0
        assert m["success_rate"] == 100.0

    def test_success_rate(self):
        m = v2.validation_metrics([0, 1, 5, -1])  # 3/4 within +-2
        assert m["success_rate"] == 75.0


# ============================================================================
# P17 — Medical safety flags
# ============================================================================
class TestMedicalFlags:
    def test_irregularity_flag_added(self):
        trend = {"variability_strength": 50}
        flags = v2.medical_flags([28, 90, 28], [5], 28.0, trend)
        codes = [f["code"] for f in flags]
        assert "increasing_irregularity" in codes
        assert all("guidance" in f for f in flags)

    def test_no_irregularity_when_low(self):
        trend = {"variability_strength": 5}
        flags = v2.medical_flags([28, 28, 28], [5], 28.0, trend)
        assert "increasing_irregularity" not in [f["code"] for f in flags]


# ============================================================================
# P12 — Audit trail determinism
# ============================================================================
class TestPredictionId:
    def test_deterministic(self):
        starts = starts_from_lengths(FIRST, [28, 28, 28])
        ends = [None, None, None, None]
        a = v2._prediction_id(starts, ends)
        b = v2._prediction_id(starts, ends)
        assert a == b
        assert len(a) == 16

    def test_changes_with_input(self):
        s1 = starts_from_lengths(FIRST, [28, 28])
        s2 = starts_from_lengths(FIRST, [29, 28])
        assert v2._prediction_id(s1, [None] * 3) != v2._prediction_id(s2, [None] * 3)


# ============================================================================
# Top-level predict() — integration across all priorities
# ============================================================================
class TestPredictIntegration:
    def test_empty(self):
        r = v2.predict([], today=date(2024, 1, 1))
        assert r["predictedDate"] is None
        assert r["confidence"] == 0
        assert r["dataSufficiency"]["level"] == 0
        assert r["engineVersion"] == v2.ENGINE_VERSION

    def test_single_cycle(self):
        r = v2.predict([{"start_date": "2024-01-01", "end_date": "2024-01-05"}],
                       today=date(2024, 2, 1))
        assert r["predictedDate"] is not None
        assert r["dataSufficiency"]["level"] == 1
        assert r["confidence"] <= 30

    def test_cold_start_population_prior(self):
        cycles = cycles_from_lengths(FIRST, [28, 29])
        r = v2.predict(cycles, today=date(2024, 4, 1))
        assert 0 < r["populationPrior"]["blend_weight"] < 1
        assert r["confidence"] <= r["dataSufficiency"]["max_confidence"]

    def test_full_history_fields(self):
        cycles = cycles_from_lengths(FIRST, REGULAR)
        r = v2.predict(cycles, today=date(2025, 6, 1))
        # core (v1-compatible) fields
        for key in ("predictedDate", "earliestDate", "latestDate", "confidence",
                    "regularity", "cycleLengthPrediction", "probabilityDistribution",
                    "fertileWindowStart", "fertileWindowEnd", "ovulationDate",
                    "healthFlags", "trendInsights", "profile"):
            assert key in r
        # v2 additions
        for key in ("engineVersion", "algorithmVersion", "models", "finalPrediction",
                    "modelWeights", "predictionErrors", "confidenceSource",
                    "reliabilityIndex", "predictionIntervals", "changePoints",
                    "outlierClassifications", "dataSufficiency", "trendForecast",
                    "validationMetrics", "populationPrior", "benchmark", "auditTrail"):
            assert key in r
        assert r["reliabilityIndex"]["score"] >= 0
        assert sum(r["modelWeights"].values()) == pytest.approx(1.0, abs=1e-3)

    def test_determinism(self):
        cycles = cycles_from_lengths(FIRST, REGULAR)
        r1 = v2.predict(cycles, today=date(2025, 6, 1), generated_at="2025-06-01T00:00:00")
        r2 = v2.predict(cycles, today=date(2025, 6, 1), generated_at="2099-01-01T00:00:00")
        # generated_at is metadata only -> must NOT change any prediction value
        r1.pop("auditTrail"); r2.pop("auditTrail")
        assert r1 == r2

    def test_clamps_to_physiological_range(self):
        # extreme tiny cycles shouldn't predict below the floor
        cycles = cycles_from_lengths(FIRST, [16, 16, 16, 16, 16])
        r = v2.predict(cycles, today=date(2024, 6, 1))
        assert v2.MIN_CYCLE_LENGTH <= r["cycleLengthPrediction"] <= v2.MAX_CYCLE_LENGTH

    def test_ignores_invalid_and_reversed_dates(self):
        cycles = [
            {"start_date": "not-a-date"},
            {"start_date": "2024-01-01", "end_date": "2023-12-01"},  # end < start
            {"start_date": "2024-01-29"},
        ]
        r = v2.predict(cycles, today=date(2024, 3, 1))
        assert r["profile"]["cycle_count"] == 2

    def test_change_point_in_output(self):
        cycles = cycles_from_lengths(FIRST, [28, 28, 28, 28, 35, 35, 35, 35])
        r = v2.predict(cycles, today=date(2025, 1, 1))
        if r["changePoints"]:
            assert r["changePoints"][0]["date"] is not None

    def test_outlier_in_audit(self):
        cycles = cycles_from_lengths(FIRST, [28, 28, 28, 28, 5, 28, 28])
        r = v2.predict(cycles, today=date(2025, 1, 1))
        assert any(o["outlier_type"] == "Logging Error"
                   for o in r["outlierClassifications"])
        assert r["auditTrail"]["excluded_cycles"]

    def test_legacy_trend_insights_shape(self):
        cycles = cycles_from_lengths(FIRST, [26, 27, 28, 29, 30, 31, 32, 33])
        r = v2.predict(cycles, today=date(2025, 1, 1))
        assert isinstance(r["trendInsights"], list)
        for t in r["trendInsights"]:
            assert "type" in t and "message" in t

    def test_performance_under_100ms(self):
        # 10 years of monthly cycles
        long_lengths = [28 + (i % 5) - 2 for i in range(130)]
        cycles = cycles_from_lengths(date(2014, 1, 1), long_lengths)
        t = time.time()
        v2.predict(cycles, today=date(2025, 1, 1))
        elapsed = (time.time() - t) * 1000
        assert elapsed < 100, f"engine took {elapsed:.1f}ms"


class TestLegacyTrendInsights:
    def test_decreasing_and_change_point(self):
        trend = {"cycle_length_strength": -20, "variability_strength": -20,
                 "period_length_strength": -20}
        cps = [{"type": "increase", "shift_days": 5,
                "new_baseline": 33, "previous_baseline": 28}]
        out = v2._legacy_trend_insights(trend, cps)
        types = [t["type"] for t in out]
        assert "cycle_length" in types
        assert "change_point" in types

    def test_increasing(self):
        trend = {"cycle_length_strength": 20, "variability_strength": 20,
                 "period_length_strength": 20}
        out = v2._legacy_trend_insights(trend, [])
        assert all(t["direction"] == "increasing" for t in out)
