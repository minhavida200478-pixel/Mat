"""Exhaustive unit tests for the MAT period prediction engine.

These are PURE unit tests — they import prediction_engine directly and never hit
the network or the database, so they are fast, deterministic and give near-total
coverage of the engine's statistical logic.

Run:  cd /app/backend && python -m pytest tests/test_prediction_engine.py -v
"""
from __future__ import annotations

import time
from datetime import date, timedelta

import pytest

import prediction_engine as pe


# ----------------------------- helpers -----------------------------
def starts_from_lengths(first: date, lengths):
    """Build period-start dates from a starting date + list of cycle lengths."""
    s = [first]
    for L in lengths:
        s.append(s[-1] + timedelta(days=L))
    return s


def cycles_from_lengths(first: date, lengths, period_len=5):
    """Build cycle dicts (with end_date) from a list of cycle lengths."""
    starts = starts_from_lengths(first, lengths)
    out = []
    for s in starts:
        out.append({"start_date": s.isoformat(),
                    "end_date": (s + timedelta(days=period_len - 1)).isoformat()})
    return out


# ----------------------------- period length -----------------------------
class TestPeriodLength:
    def test_inclusive(self):
        assert pe.period_length(date(2026, 6, 1), date(2026, 6, 5)) == 5

    def test_single_day(self):
        assert pe.period_length(date(2026, 6, 1), date(2026, 6, 1)) == 1


# ----------------------------- cycle length -----------------------------
class TestCycleLength:
    def test_consecutive_starts(self):
        starts = [date(2026, 1, 1), date(2026, 1, 29), date(2026, 2, 26)]
        assert pe.cycle_lengths_from_starts(starts) == [28, 28]

    def test_unsorted_input_is_sorted(self):
        starts = [date(2026, 2, 26), date(2026, 1, 1), date(2026, 1, 29)]
        assert pe.cycle_lengths_from_starts(starts) == [28, 28]

    def test_empty_and_single(self):
        assert pe.cycle_lengths_from_starts([]) == []
        assert pe.cycle_lengths_from_starts([date(2026, 1, 1)]) == []


# ----------------------------- median / mean / std -----------------------------
class TestStats:
    def test_median(self):
        assert pe.median_value([1, 2, 3, 4, 5]) == 3
        assert pe.median_value([]) is None

    def test_mean(self):
        assert pe.mean_value([2, 4, 6]) == 4
        assert pe.mean_value([]) is None

    def test_std_dev_needs_two(self):
        assert pe.std_dev([5]) == 0.0
        assert pe.std_dev([]) == 0.0
        assert pe.std_dev([28, 28, 28]) == 0.0
        assert pe.std_dev([26, 30]) == pytest.approx(2.0)


# ----------------------------- MAD -----------------------------
class TestMAD:
    def test_basic(self):
        # values 1..5, median 3, abs devs [2,1,0,1,2] -> median 1
        assert pe.median_absolute_deviation([1, 2, 3, 4, 5]) == 1.0

    def test_identical_zero(self):
        assert pe.median_absolute_deviation([28, 28, 28]) == 0.0

    def test_empty(self):
        assert pe.median_absolute_deviation([]) == 0.0


# ----------------------------- outlier detection -----------------------------
class TestOutliers:
    def test_too_few_cycles(self):
        assert pe.detect_outliers([28, 30]) == [False, False]

    def test_identical_no_outliers(self):
        assert pe.detect_outliers([28, 28, 28, 28]) == [False] * 4

    def test_detects_extreme(self):
        # one huge value should be flagged
        lengths = [28, 29, 28, 27, 28, 90]
        flags = pe.detect_outliers(lengths)
        assert flags[-1] is True
        assert flags.count(True) == 1

    def test_regular_data_no_false_positive(self):
        lengths = [28, 29, 27, 28, 30, 26]
        assert all(f is False for f in pe.detect_outliers(lengths))

    def test_mad_zero_extreme_still_flagged(self):
        # Most cycles identical (MAD == 0) + one missed-period gap: the extreme
        # MUST still be flagged via the MeanAD fallback.
        lengths = [28, 28, 28, 28, 28, 28, 28, 28, 28, 95]
        flags = pe.detect_outliers(lengths)
        assert flags[-1] is True
        assert flags.count(True) == 1

    def test_mad_zero_trivial_variation_not_flagged(self):
        # MAD == 0 but the lone deviation is clinically trivial (3 days) and below
        # the absolute floor -> must NOT be flagged.
        lengths = [28, 28, 28, 28, 28, 28, 28, 28, 28, 31]
        assert all(f is False for f in pe.detect_outliers(lengths))

    def test_mad_zero_all_identical_no_outliers(self):
        assert all(f is False for f in pe.detect_outliers([28] * 10))


# ----------------------------- weighted average -----------------------------
class TestWeightedAverage:
    def test_empty(self):
        assert pe.weighted_average([]) is None

    def test_single(self):
        assert pe.weighted_average([30]) == 30

    def test_all_equal(self):
        assert pe.weighted_average([28, 28, 28, 28, 28]) == pytest.approx(28)

    def test_recent_weighted_higher(self):
        # most recent (last) is 40, rest 28 -> result pulled toward 40
        result = pe.weighted_average([28, 28, 28, 28, 40])
        plain = sum([28, 28, 28, 28, 40]) / 5
        assert result > plain  # recency weighting dominates

    def test_known_weights(self):
        # 5 cycles, values most-recent-first weights 40/25/15/10/6 normalised.
        lengths = [20, 22, 24, 26, 28]  # oldest..newest
        # most recent first: 28,26,24,22,20
        w = [0.40, 0.25, 0.15, 0.10, 0.06]
        vals = [28, 26, 24, 22, 20]
        expected = sum(v * x for v, x in zip(vals, w)) / sum(w)
        assert pe.weighted_average(lengths) == pytest.approx(expected)

    def test_outlier_weight_reduced(self):
        lengths = [28, 28, 28, 28, 90]  # newest is an outlier-ish big value
        outliers = [False, False, False, False, True]
        reduced = pe.weighted_average(lengths, outliers)
        full = pe.weighted_average(lengths, [False] * 5)
        # reducing the big recent value's weight pulls prediction back down
        assert reduced < full

    def test_older_cycles_share_four_percent(self):
        # 7 cycles: oldest two collapse into the 4% bucket
        lengths = [10, 10, 28, 28, 28, 28, 28]
        result = pe.weighted_average(lengths)
        # result dominated by the recent 28s, barely moved by the old 10s
        assert 27 < result <= 28


class TestWeightedPrediction:
    def test_none_for_empty(self):
        assert pe.weighted_prediction([]) is None

    def test_outlier_aware(self):
        lengths = [28, 29, 28, 27, 28, 95]
        # outlier-aware prediction should stay near 28, not be dragged to ~40
        assert pe.weighted_prediction(lengths) < 40


# ----------------------------- adaptive learning -----------------------------
class TestAdaptiveLearning:
    def test_no_errors_for_short_history(self):
        assert pe.backtest_errors([28, 28]) == []

    def test_perfect_history_zero_error(self):
        errors = pe.backtest_errors([28, 28, 28, 28, 28, 28])
        assert all(abs(e) < 1e-9 for e in errors)
        assert pe.accuracy_from_errors(errors) == 100
        assert pe.adaptive_bias(errors) == pytest.approx(0.0, abs=1e-9)

    def test_bias_positive_when_underpredicting(self):
        # steadily increasing cycles -> engine under-predicts -> positive bias
        lengths = [24, 26, 28, 30, 32, 34]
        errors = pe.backtest_errors(lengths)
        assert pe.adaptive_bias(errors) > 0

    def test_accuracy_none_without_errors(self):
        assert pe.accuracy_from_errors([]) is None

    def test_accuracy_drops_with_error(self):
        assert pe.accuracy_from_errors([5, -5, 5]) < pe.accuracy_from_errors([1, -1, 1])


# ----------------------------- confidence -----------------------------
class TestConfidence:
    def test_zero_cycles(self):
        assert pe.confidence_score(0, 0.0, None, 0.0) <= 15

    def test_more_cycles_more_confidence(self):
        low = pe.confidence_score(1, 1.0, None, 50)
        high = pe.confidence_score(12, 1.0, 95, 100)
        assert high > low

    def test_lower_variability_higher_confidence(self):
        steady = pe.confidence_score(8, 0.5, 90, 80)
        noisy = pe.confidence_score(8, 7.0, 90, 80)
        assert steady > noisy

    def test_bounded_0_100(self):
        assert 0 <= pe.confidence_score(50, 0.0, 100, 100) <= 100
        assert 0 <= pe.confidence_score(0, 50.0, 0, 0) <= 100


class TestDataQuality:
    def test_zero_cycles(self):
        assert pe.data_quality_score(0, [], []) == 0.0

    def test_full_completeness(self):
        dq = pe.data_quality_score(6, [5, 5, 5, 5, 5, 5], [28] * 6)
        assert dq == pytest.approx(100, abs=0.1)

    def test_partial_completeness(self):
        dq = pe.data_quality_score(6, [5, 5, 5], [28] * 6)  # half periods logged
        assert 0 < dq < 100


# ----------------------------- classification -----------------------------
class TestClassification:
    def test_unknown_under_three(self):
        assert pe.classify_regularity(2, 0.0) == "Unknown"

    def test_very_regular(self):
        assert pe.classify_regularity(6, 1.0) == "Very Regular"

    def test_regular(self):
        assert pe.classify_regularity(6, 3.0) == "Regular"

    def test_moderately_irregular(self):
        assert pe.classify_regularity(6, 5.5) == "Moderately Irregular"
        assert pe.classify_regularity(6, 7.0) == "Moderately Irregular"

    def test_highly_irregular(self):
        assert pe.classify_regularity(6, 9.0) == "Highly Irregular"


class TestRegularityVariability:
    def test_regularity_inverse_of_std(self):
        assert pe.regularity_from_std(0.0) == 100
        assert pe.regularity_from_std(10.0) == 0
        assert 0 <= pe.regularity_from_std(3.0) <= 100

    def test_variability_score(self):
        assert pe.variability_score(0.0) == 0.0
        assert pe.variability_score(10.0) == 100


# ----------------------------- prediction window -----------------------------
class TestPredictionWindow:
    def test_symmetric_window(self):
        d = date(2026, 6, 20)
        earliest, latest, margin = pe.prediction_window(d, 2.0, 87)
        assert earliest < d < latest
        assert (d - earliest).days == margin
        assert (latest - d).days == margin

    def test_low_confidence_widens(self):
        d = date(2026, 6, 20)
        _, _, m_high = pe.prediction_window(d, 2.0, 95)
        _, _, m_low = pe.prediction_window(d, 2.0, 30)
        assert m_low >= m_high

    def test_minimum_margin_one(self):
        d = date(2026, 6, 20)
        _, _, margin = pe.prediction_window(d, 0.0, 100)
        assert margin >= 1


# ----------------------------- probability distribution -----------------------------
class TestProbabilityDistribution:
    def test_14_day_window(self):
        dist = pe.probability_distribution(date(2026, 6, 20), 2.0, 2, 87)
        assert len(dist) == 14

    def test_peaks_on_predicted_day(self):
        dist = pe.probability_distribution(date(2026, 6, 20), 2.0, 2, 87)
        peak = max(dist, key=lambda x: x["probability"])
        assert peak["dayOffset"] == 0
        assert peak["date"] == "2026-06-20"

    def test_probabilities_bounded(self):
        dist = pe.probability_distribution(date(2026, 6, 20), 2.0, 2, 87)
        assert all(0 <= x["probability"] <= 100 for x in dist)

    def test_symmetric_decay(self):
        dist = pe.probability_distribution(date(2026, 6, 20), 2.0, 2, 87)
        by_offset = {x["dayOffset"]: x["probability"] for x in dist}
        assert by_offset[-2] == by_offset[2]
        assert by_offset[0] > by_offset[3]


# ----------------------------- trend detection -----------------------------
class TestTrends:
    def test_no_trends_short_history(self):
        assert pe.detect_trends([28, 28], []) == []

    def test_lengthening(self):
        trends = pe.detect_trends([26, 26, 30, 31], [])
        assert any(t["type"] == "cycle_length" and t["direction"] == "increasing"
                   for t in trends)

    def test_shortening(self):
        trends = pe.detect_trends([32, 31, 26, 25], [])
        assert any(t["type"] == "cycle_length" and t["direction"] == "decreasing"
                   for t in trends)

    def test_increasing_variability(self):
        trends = pe.detect_trends([28, 28, 20, 36], [])
        assert any(t["type"] == "variability" and t["direction"] == "increasing"
                   for t in trends)

    def test_period_lengthening(self):
        trends = pe.detect_trends([], [4, 4, 6, 7])
        assert any(t["type"] == "period_length" and t["direction"] == "increasing"
                   for t in trends)


# ----------------------------- health flags -----------------------------
class TestHealthFlags:
    def test_short_cycle(self):
        flags = pe.health_flags([18, 28, 28], [], 28)
        assert any(f["code"] == "short_cycle" for f in flags)

    def test_long_cycle(self):
        flags = pe.health_flags([28, 40, 28], [], 28)
        assert any(f["code"] == "long_cycle" for f in flags)

    def test_very_long_cycle(self):
        flags = pe.health_flags([28, 100], [], 28)
        assert any(f["code"] == "very_long_cycle" for f in flags)

    def test_long_period(self):
        flags = pe.health_flags([28, 28], [12], 28)
        assert any(f["code"] == "long_period" for f in flags)

    def test_sudden_change(self):
        flags = pe.health_flags([28, 42], [], 28)
        assert any(f["code"] == "sudden_change" for f in flags)

    def test_repeated_missed(self):
        flags = pe.health_flags([28, 60, 28, 65], [], 28)
        assert any(f["code"] == "repeated_missed" for f in flags)

    def test_healthy_no_flags(self):
        flags = pe.health_flags([28, 29, 27, 28], [5, 5, 5, 5], 28)
        assert flags == []


# ----------------------------- fertile window -----------------------------
class TestFertileWindow:
    def test_window_relative_to_predicted(self):
        # ovulation = predicted - 14; window = ovulation-5 .. ovulation+1
        fs, fe, ov = pe.fertile_window(date(2026, 7, 2))
        assert ov == date(2026, 6, 18)
        assert fs == date(2026, 6, 13)
        assert fe == date(2026, 6, 19)

    def test_window_span_is_seven_days(self):
        fs, fe, _ = pe.fertile_window(date(2026, 7, 2))
        assert (fe - fs).days == 6  # 7 inclusive days

    def test_predict_exposes_fertile_window(self):
        out = pe.predict([{"start_date": "2026-06-01"}], today=date(2026, 6, 20))
        # predicted Jun 29 -> ovulation Jun 15, window Jun 10..Jun 16
        assert out["predictedDate"] == "2026-06-29"
        assert out["ovulationDate"] == "2026-06-15"
        assert out["fertileWindowStart"] == "2026-06-10"
        assert out["fertileWindowEnd"] == "2026-06-16"

    def test_predict_fertile_null_without_data(self):
        out = pe.predict([], today=date(2026, 6, 20))
        assert out["fertileWindowStart"] is None
        assert out["fertileWindowEnd"] is None
        assert out["ovulationDate"] is None


# ----------------------------- top-level predict -----------------------------
class TestPredict:
    def test_empty_history(self):
        out = pe.predict([], today=date(2026, 6, 20))
        assert out["predictedDate"] is None
        assert out["regularity"] == "Unknown"
        assert out["confidence"] >= 0
        assert out["probabilityDistribution"] == []

    def test_single_cycle_uses_default(self):
        out = pe.predict([{"start_date": "2026-06-01"}], today=date(2026, 6, 20))
        assert out["cycleLengthPrediction"] == pe.DEFAULT_CYCLE_LENGTH
        assert out["predictedDate"] == "2026-06-29"
        assert out["regularity"] == "Unknown"

    def test_regular_user_full_response(self):
        cycles = cycles_from_lengths(date(2025, 1, 1), [28] * 11)  # 12 starts
        out = pe.predict(cycles, today=date(2026, 6, 20))
        # response contract keys
        for key in ("predictedDate", "earliestDate", "latestDate", "confidence",
                    "regularity", "cycleLengthPrediction", "probabilityDistribution",
                    "healthFlags", "trendInsights", "profile"):
            assert key in out
        assert out["cycleLengthPrediction"] == 28
        assert out["regularity"] == "Very Regular"
        assert out["confidence"] >= 70
        assert len(out["probabilityDistribution"]) == 14
        assert out["earliestDate"] < out["predictedDate"] < out["latestDate"]

    def test_irregular_user_lower_confidence(self):
        regular = pe.predict(cycles_from_lengths(date(2025, 1, 1), [28] * 8),
                             today=date(2026, 6, 20))
        irregular = pe.predict(
            cycles_from_lengths(date(2025, 1, 1), [21, 40, 24, 45, 26, 38, 22, 44]),
            today=date(2026, 6, 20))
        assert irregular["confidence"] < regular["confidence"]
        assert irregular["regularity"] in ("Moderately Irregular", "Highly Irregular")

    def test_outlier_does_not_wreck_prediction(self):
        # 8 cycles ~28 with one 95-day gap; prediction must stay sane (~28)
        cycles = cycles_from_lengths(date(2025, 1, 1), [28, 29, 27, 95, 28, 29, 28])
        out = pe.predict(cycles, today=date(2026, 6, 20))
        assert 24 <= out["cycleLengthPrediction"] <= 32
        assert out["profile"]["outlier_count"] >= 1

    def test_ignores_malformed_dates(self):
        cycles = [{"start_date": "not-a-date"},
                  {"start_date": "2026-06-01"},
                  {"start_date": "2026-06-29"}]
        out = pe.predict(cycles, today=date(2026, 6, 20))
        assert out["profile"]["cycle_count"] == 2

    def test_end_before_start_dropped(self):
        cycles = [{"start_date": "2026-06-10", "end_date": "2026-06-01"}]
        out = pe.predict(cycles, today=date(2026, 6, 20))
        # invalid end ignored -> no period length recorded
        assert out["profile"]["average_period_length"] is None

    def test_deterministic_same_input_same_output(self):
        cycles = cycles_from_lengths(date(2025, 1, 1), [28, 30, 27, 29, 28, 31])
        a = pe.predict(cycles, today=date(2026, 6, 20))
        b = pe.predict(cycles, today=date(2026, 6, 20))
        assert a == b

    def test_performance_under_100ms_10yr_history(self):
        # ~130 cycles ≈ 10 years of monthly cycles
        lengths = [28 + (i % 5) - 2 for i in range(130)]
        cycles = cycles_from_lengths(date(2014, 1, 1), lengths)
        t0 = time.perf_counter()
        pe.predict(cycles, today=date(2026, 6, 20))
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert elapsed_ms < 100, f"prediction took {elapsed_ms:.1f}ms"
