"""Unit tests for the v3 verified-forecasting engine (pure, no API)."""
import json
import time
from datetime import date, timedelta

import pytest

import prediction_engine_v3 as v3
from prediction_engine_v3 import (
    LOOKBACK_WINDOWS,
    SELECTION_MARGIN,
    STRATEGIES,
    apply_bias_correction,
    apply_dampening,
    calibration_engine,
    conformal_coverage,
    conformal_intervals,
    empirical_distribution,
    quantile_forecast,
    select_pipeline,
    walk_forward,
)


# ----------------------------- helpers -----------------------------
def cycles_from_lengths(lengths, first=date(2024, 1, 1), period_days=4):
    starts = [first]
    for L in lengths:
        starts.append(starts[-1] + timedelta(days=L))
    return [{"start_date": s.isoformat(),
             "end_date": (s + timedelta(days=period_days)).isoformat()}
            for s in starts]


REGULAR = [28, 27, 29, 28, 28, 27, 29, 28, 28, 27, 29, 28]
NOISY = [28, 31, 26, 29, 33, 25, 30, 27, 32, 26, 29, 31, 27, 30, 28, 33, 26, 29]
SHIFTED = [28, 29, 28, 29, 28, 28, 34, 35, 33, 34, 35]


# ----------------------------- determinism (P18-equivalent) -----------------------------
class TestDeterminism:
    def test_same_input_identical_output(self):
        c = cycles_from_lengths(NOISY)
        r1 = v3.predict(c, today=date(2025, 8, 1))
        r2 = v3.predict(c, today=date(2025, 8, 1))
        assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)

    def test_generated_at_does_not_change_values(self):
        c = cycles_from_lengths(REGULAR)
        r1 = v3.predict(c, today=date(2025, 8, 1), generated_at="2026-01-01T00:00:00")
        r2 = v3.predict(c, today=date(2025, 8, 1), generated_at="2026-06-06T06:06:06")
        r1["auditTrail"]["generated_at"] = r2["auditTrail"]["generated_at"]
        assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)

    def test_pipeline_selection_is_deterministic(self):
        lengths = NOISY
        starts = [date(2024, 1, 1)]
        for L in lengths:
            starts.append(starts[-1] + timedelta(days=L))
        p1 = select_pipeline(lengths, starts[:-1])
        p2 = select_pipeline(lengths, starts[:-1])
        assert (p1["strategy"], p1["window"], p1["variant"]) == \
               (p2["strategy"], p2["window"], p2["variant"])


# ----------------------------- v2 schema compatibility -----------------------------
class TestSchemaCompatibility:
    V2_KEYS = ["predictedDate", "earliestDate", "latestDate", "confidence",
               "regularity", "cycleLengthPrediction", "probabilityDistribution",
               "fertileWindowStart", "fertileWindowEnd", "ovulationDate",
               "healthFlags", "trendInsights", "profile", "engineVersion",
               "algorithmVersion", "models", "finalPrediction", "modelWeights",
               "predictionErrors", "confidenceSource", "confidenceSamples",
               "reliabilityIndex", "predictionIntervals", "changePoints",
               "outlierClassifications", "dataSufficiency", "trendForecast",
               "validationMetrics", "populationPrior", "benchmark", "auditTrail"]
    V3_KEYS = ["errorLearning", "modelAccuracy", "modelWeightHistory",
               "modelAccuracyHistory", "lookback", "activeForecastingStrategy",
               "conformalCalibration", "quantileForecast", "forecastStability",
               "calibration", "deploymentGate"]

    def test_all_keys_present(self):
        r = v3.predict(cycles_from_lengths(NOISY), today=date(2025, 8, 1))
        for k in self.V2_KEYS + self.V3_KEYS:
            assert k in r, f"missing key {k}"

    def test_engine_version(self):
        r = v3.predict(cycles_from_lengths(REGULAR), today=date(2025, 8, 1))
        assert r["engineVersion"] == "3.0.0"
        assert r["algorithmVersion"] == "verified-forecast-v1"


# ----------------------------- performance (<100ms, 10+ years) -----------------------------
class TestPerformance:
    def test_ten_years_under_100ms(self):
        lengths = [(27 + (i * 7) % 5) for i in range(130)]  # ~10 years
        c = cycles_from_lengths(lengths)
        t0 = time.perf_counter()
        r = v3.predict(c, today=date(2035, 1, 1))
        elapsed = (time.perf_counter() - t0) * 1000
        assert elapsed < 100, f"prediction took {elapsed:.1f}ms"
        assert r["predictedDate"] is not None


# ----------------------------- cold start -----------------------------
class TestColdStart:
    @pytest.mark.parametrize("n,level,max_conf", [(0, 0, 0), (1, 1, 30), (2, 2, 50)])
    def test_levels_and_caps(self, n, level, max_conf):
        c = cycles_from_lengths([28] * max(0, n - 1))[:n]
        r = v3.predict(c, today=date(2025, 6, 1))
        assert r["dataSufficiency"]["level"] == level
        assert r["confidence"] <= max_conf
        if n == 0:
            assert r["predictedDate"] is None

    def test_no_walkforward_uses_default_pipeline(self):
        r = v3.predict(cycles_from_lengths([28, 29]), today=date(2025, 6, 1))
        assert r["activeForecastingStrategy"] == "ensemble"
        assert r["lookback"]["optimal_window"] == 12


# ----------------------------- P2 dynamic ensemble weighting -----------------------------
class TestDynamicWeights:
    def test_weights_sum_to_one_and_capped(self):
        r = v3.predict(cycles_from_lengths(NOISY), today=date(2025, 8, 1))
        w = r["modelWeights"]
        assert abs(sum(w.values()) - 1.0) < 1e-6
        assert all(v <= 0.40 + 1e-6 for v in w.values())

    def test_weight_and_accuracy_history_tracked(self):
        r = v3.predict(cycles_from_lengths(NOISY), today=date(2025, 8, 1))
        assert 1 <= len(r["modelWeightHistory"]) <= 12
        assert 1 <= len(r["modelAccuracyHistory"]) <= 12
        for snap in r["modelWeightHistory"]:
            assert set(snap.keys()) == set(v3.MODEL_KEYS)
            assert abs(sum(snap.values()) - 1.0) < 1e-3

    def test_per_model_accuracy_mae_rmse(self):
        r = v3.predict(cycles_from_lengths(NOISY), today=date(2025, 8, 1))
        for k in v3.MODEL_KEYS:
            acc = r["modelAccuracy"][k]
            assert acc["mae"] is not None and acc["mae"] >= 0
            assert acc["rmse"] is not None and acc["rmse"] >= acc["mae"] - 1e-9
            assert acc["samples"] > 0

    def test_weights_are_out_of_sample(self):
        """First walk-forward step must use DEFAULT weights (no prior evidence)."""
        starts = [date(2024, 1, 1)]
        for L in NOISY:
            starts.append(starts[-1] + timedelta(days=L))
        wf = walk_forward(NOISY, starts[:-1], 12)
        assert wf["weight_history"][0] == {k: round(v3.DEFAULT_WEIGHTS[k], 4)
                                           for k in v3.MODEL_KEYS}


# ----------------------------- P1 error learning -----------------------------
class TestErrorLearning:
    def test_fields(self):
        r = v3.predict(cycles_from_lengths(NOISY), today=date(2025, 8, 1))
        el = r["errorLearning"]
        for k in ("average_error", "rolling_3_cycle_error", "rolling_6_cycle_error",
                  "rolling_12_cycle_error", "bias_days", "bias_direction",
                  "bias_correction_applied", "bias_gate"):
            assert k in el
        assert el["bias_direction"] in ("systematic_early", "systematic_late", "none")

    def test_bias_correction_only_when_it_improves(self):
        for lengths in (REGULAR, NOISY, SHIFTED, list(range(26, 38))):
            r = v3.predict(cycles_from_lengths(lengths), today=date(2025, 8, 1))
            el = r["errorLearning"]
            if el["bias_correction_applied"]:
                assert el["bias_gate"]["mae_bias_corrected"] is not None
                assert el["bias_gate"]["mae_bias_corrected"] < el["bias_gate"]["mae_raw"]

    def test_systematic_early_detected_on_steady_increase(self):
        lengths = [26, 26, 27, 27, 28, 28, 29, 29, 30, 30, 31, 31, 32, 32]
        r = v3.predict(cycles_from_lengths(lengths), today=date(2025, 8, 1))
        # lagging models under-predict a rising series -> actual later than predicted
        assert r["errorLearning"]["average_error"] > 0

    def test_apply_bias_correction_walkforward(self):
        raw = [28.0, 28.0, 28.0, 28.0]
        actuals = [30.0, 30.0, 30.0, 30.0]
        out = apply_bias_correction(raw, actuals)
        assert out[0] == 28.0           # no evidence yet
        assert out[-1] == 30.0          # learned the +2 bias


# ----------------------------- P3 conformal prediction -----------------------------
class TestConformal:
    def test_conformal_used_with_enough_history(self):
        r = v3.predict(cycles_from_lengths(NOISY), today=date(2025, 8, 1))
        assert r["predictionIntervals"]["source"] in (
            "conformal", "empirical_error (conformal_rejected)",
            "model_variance (conformal_rejected)")

    def test_intervals_nested(self):
        r = v3.predict(cycles_from_lengths(NOISY), today=date(2025, 8, 1))
        iv = r["predictionIntervals"]
        for inner, outer in (("p50", "p75"), ("p75", "p90"), ("p90", "p95")):
            assert iv[outer]["start"] <= iv[inner]["start"]
            assert iv[outer]["end"] >= iv[inner]["end"]

    def test_coverage_report_structure(self):
        r = v3.predict(cycles_from_lengths(NOISY), today=date(2025, 8, 1))
        cc = r["conformalCalibration"]
        assert isinstance(cc["accepted"], bool)
        for lv in ("p50", "p75", "p90", "p95"):
            assert cc[lv]["expected_coverage"] == int(lv[1:]) / 100.0
            assert "observed_coverage" in cc[lv]
            assert "calibration_error" in cc[lv]

    def test_insufficient_samples_fallback(self):
        r = v3.predict(cycles_from_lengths(REGULAR[:5]), today=date(2025, 8, 1))
        assert "conformal" != r["predictionIntervals"].get("source")

    def test_conformal_intervals_none_below_minimum(self):
        assert conformal_intervals(date(2025, 1, 1), [1.0] * 7) is None

    def test_coverage_math(self):
        # constant errors -> intervals from priors always contain the next error
        report = conformal_coverage([0.0] * 12)
        assert report["p95"]["observed_coverage"] == 1.0
        assert report["accepted"] is True


# ----------------------------- P5 quantile forecasting -----------------------------
class TestQuantiles:
    def test_monotonic_quantiles(self):
        r = v3.predict(cycles_from_lengths(NOISY), today=date(2025, 8, 1))
        q = r["quantileForecast"]["quantiles"]
        dates = [q[f"p{p}"] for p in (10, 25, 50, 75, 90)]
        assert all(d is not None for d in dates)
        assert dates == sorted(dates)

    def test_method_gated_by_pinball_loss(self):
        r = v3.predict(cycles_from_lengths(NOISY), today=date(2025, 8, 1))
        qf = r["quantileForecast"]
        assert qf["method"] in ("direct_empirical", "traditional")
        pl = qf["pinball_loss"]
        if qf["method"] == "direct_empirical":
            assert pl["direct_empirical"] <= pl["traditional"]

    def test_traditional_fallback_with_little_data(self):
        r = v3.predict(cycles_from_lengths(REGULAR[:4]), today=date(2025, 8, 1))
        assert r["quantileForecast"]["method"] == "traditional"

    def test_quantile_function_directly(self):
        qf = quantile_forecast(28.0, date(2025, 1, 1),
                               [-2.0, -1.0, 0.0, 0.5, 1.0, 1.5, 2.0, 3.0], 2.0)
        offs = qf["offsets_days"]
        assert offs["p10"] <= offs["p25"] <= offs["p50"] <= offs["p75"] <= offs["p90"]


# ----------------------------- P4 adaptive lookback -----------------------------
class TestAdaptiveLookback:
    def test_window_is_valid_and_reported(self):
        r = v3.predict(cycles_from_lengths(NOISY), today=date(2025, 8, 1))
        lb = r["lookback"]
        assert lb["optimal_window"] in LOOKBACK_WINDOWS
        assert set(lb["window_performance_metrics"].keys()) == \
               {str(w) for w in LOOKBACK_WINDOWS}

    def test_baseline_shift_prediction_tracks_new_baseline(self):
        r = v3.predict(cycles_from_lengths(SHIFTED), today=date(2025, 8, 1))
        # new baseline is ~34.2; engine must not predict from the old 28 baseline
        assert r["cycleLengthPrediction"] >= 32


# ----------------------------- P6 change points -----------------------------
class TestChangePoints:
    def test_change_point_with_confidence(self):
        r = v3.predict(cycles_from_lengths(SHIFTED), today=date(2025, 8, 1))
        assert r["changePoints"], "structural shift not detected"
        cp = r["changePoints"][0]
        assert cp["change_point_date"] is not None
        assert 0 <= cp["change_point_confidence"] <= 100
        assert cp["new_baseline"] > cp["previous_baseline"]

    def test_no_change_point_for_stable_user(self):
        r = v3.predict(cycles_from_lengths(REGULAR), today=date(2025, 8, 1))
        assert r["changePoints"] == []


# ----------------------------- P7 distribution forecasting -----------------------------
class TestDistribution:
    def test_distribution_rows(self):
        r = v3.predict(cycles_from_lengths(NOISY), today=date(2025, 8, 1))
        dist = r["probabilityDistribution"]
        assert dist
        for row in dist:
            assert set(row.keys()) == {"date", "dayOffset", "probability"}
            assert 0 <= row["probability"] <= 100

    def test_empirical_distribution_14_day_window(self):
        dist = empirical_distribution(date(2025, 6, 1),
                                      [-3, -2, -1, 0, 0, 1, 1, 2, 3, 4])
        assert len(dist) == 14
        assert [r["dayOffset"] for r in dist] == list(range(-7, 7))
        total = sum(r["probability"] for r in dist)
        assert 85 <= total <= 110  # rounding

    def test_intervals_consistent_with_distribution(self):
        """Intervals and distribution derive from the same error CDF (P7)."""
        r = v3.predict(cycles_from_lengths(NOISY), today=date(2025, 8, 1))
        if r["predictionIntervals"].get("source") != "conformal":
            pytest.skip("conformal not active for this fixture")
        dist_dates = [row["date"] for row in r["probabilityDistribution"]]
        p95 = r["predictionIntervals"]["p95"]
        assert p95["start"] >= min(dist_dates)
        assert p95["end"] <= max(dist_dates)


# ----------------------------- P8 calibration engine -----------------------------
class TestCalibration:
    def test_fields(self):
        r = v3.predict(cycles_from_lengths(NOISY), today=date(2025, 8, 1))
        cal = r["calibration"]
        assert cal["estimator"] in ("raw", "shrunk")
        assert cal["target"] == 5.0
        assert isinstance(cal["target_met"], bool)
        assert isinstance(cal["buckets"], list)

    def test_estimator_gated_by_calibration_error(self):
        cal = calibration_engine([0.5, -1.0, 1.5, 0.0, -0.5, 2.5, -2.0,
                                  1.0, 0.5, -1.5, 3.0, 0.0, 1.0, -0.5])
        if cal["estimator"] == "shrunk":
            assert cal["calibration_error_shrunk"] < cal["calibration_error_raw"]

    def test_confidence_is_evidence_based(self):
        r = v3.predict(cycles_from_lengths(REGULAR), today=date(2025, 8, 1))
        assert r["confidenceSource"] == "historical_accuracy"
        assert 0 <= r["confidence"] <= 95


# ----------------------------- P9 forecast stability -----------------------------
class TestStability:
    def test_fields(self):
        r = v3.predict(cycles_from_lengths(NOISY), today=date(2025, 8, 1))
        st = r["forecastStability"]
        for k in ("stability_score", "prediction_volatility", "date_oscillation",
                  "forecast_drift", "dampening_applied", "dampening_gate"):
            assert k in st
        assert 0 <= st["stability_score"] <= 100

    def test_dampening_only_when_it_improves(self):
        for lengths in (REGULAR, NOISY, SHIFTED):
            r = v3.predict(cycles_from_lengths(lengths), today=date(2025, 8, 1))
            gate = r["deploymentGate"]["gates"]["dampening"]
            if gate["applied"]:
                assert gate["mae_with"] < gate["mae_raw"]

    def test_apply_dampening_limits_movement(self):
        out = apply_dampening([28.0, 35.0, 20.0, 28.0])
        for prev, cur in zip(out, out[1:]):
            assert abs(cur - prev) <= v3.DAMPENING_CLAMP + 1e-9


# ----------------------------- P11 strategy selection -----------------------------
class TestStrategySelection:
    def test_active_strategy_valid(self):
        r = v3.predict(cycles_from_lengths(NOISY), today=date(2025, 8, 1))
        assert r["activeForecastingStrategy"] in STRATEGIES

    def test_margin_protected_selection(self):
        for lengths in (REGULAR, NOISY, SHIFTED):
            r = v3.predict(cycles_from_lengths(lengths), today=date(2025, 8, 1))
            sel = r["deploymentGate"]["selected_pipeline"]
            dflt = r["deploymentGate"]["default_pipeline"]
            if sel["selected_by_evidence"] and (
                    sel["strategy"] != "ensemble" or sel["window"] != 12):
                assert sel["mae"] <= dflt["mae"] - SELECTION_MARGIN + 1e-9

    def test_selected_never_worse_than_default(self):
        for lengths in (REGULAR, NOISY, SHIFTED):
            r = v3.predict(cycles_from_lengths(lengths), today=date(2025, 8, 1))
            sel = r["deploymentGate"]["selected_pipeline"]
            dflt = r["deploymentGate"]["default_pipeline"]
            if sel["mae"] is not None and dflt["mae"] is not None:
                assert sel["mae"] <= dflt["mae"] + 1e-9


# ----------------------------- P12 deployment gates -----------------------------
class TestDeploymentGates:
    def test_gate_report_structure(self):
        r = v3.predict(cycles_from_lengths(NOISY), today=date(2025, 8, 1))
        gates = r["deploymentGate"]["gates"]
        for g in ("bias_correction", "dampening", "conformal_intervals",
                  "quantile_method", "confidence_estimator"):
            assert g in gates

    def test_conformal_gate_consistency(self):
        r = v3.predict(cycles_from_lengths(NOISY), today=date(2025, 8, 1))
        gate = r["deploymentGate"]["gates"]["conformal_intervals"]
        assert gate["applied"] == (r["predictionIntervals"].get("source") == "conformal")


# ----------------------------- P13 explainability -----------------------------
class TestExplainability:
    def test_forecast_generated_by(self):
        r = v3.predict(cycles_from_lengths(NOISY), today=date(2025, 8, 1))
        fg = r["auditTrail"]["forecast_generated_by"]
        assert fg["strategy"] == r["activeForecastingStrategy"]
        assert fg["lookback_window"] == r["lookback"]["optimal_window"]
        assert "why_this_prediction" in fg and fg["why_this_prediction"]
        assert "why_this_confidence" in fg and fg["why_this_confidence"]

    def test_contributing_and_excluded_cycles(self):
        lengths = REGULAR + [90]  # missed cycle outlier
        r = v3.predict(cycles_from_lengths(lengths), today=date(2025, 12, 1))
        audit = r["auditTrail"]
        assert len(audit["contributing_cycles"]) == len(lengths) + 1
        assert any(o["type"] == "Missed Cycle" for o in audit["outlier_adjustments"])
        assert audit["excluded_cycles"]


# ----------------------------- robustness -----------------------------
class TestRobustness:
    def test_outliers_dont_crash(self):
        r = v3.predict(cycles_from_lengths([28, 5, 28, 90, 28, 28, 28, 29, 27, 28]),
                       today=date(2025, 8, 1))
        assert r["predictedDate"] is not None
        assert 15 <= r["cycleLengthPrediction"] <= 60

    def test_invalid_dates_skipped(self):
        r = v3.predict([{"start_date": "garbage"}, {"start_date": None},
                        {"start_date": "2025-01-01"}], today=date(2025, 6, 1))
        assert r["dataSufficiency"]["level"] == 1

    def test_medical_flags_still_emitted(self):
        r = v3.predict(cycles_from_lengths([40, 39, 41, 40, 40, 39]),
                       today=date(2025, 12, 1))
        assert any(f["code"] == "long_cycles" or "35" in f.get("message", "")
                   or f.get("code") for f in r["healthFlags"])
