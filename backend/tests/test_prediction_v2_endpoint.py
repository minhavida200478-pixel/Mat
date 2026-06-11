"""Phase 2 (v2 engine) live API tests for GET /api/prediction.

Targets the Phase 2 contract:
  - engineVersion in ("2.0.0", "3.0.0")
  - reliabilityIndex (score 0-100 + classification)
  - predictionIntervals (p50/p75/p90/p95) with half_width_days non-decreasing
  - dataSufficiency level/label/max_confidence and confidence cap enforcement
  - modelWeights sum ~1.0, no single model > 0.40 (MAX_MODEL_WEIGHT)
  - predictionErrors (rolling 3/6/12 + bias_days)
  - validationMetrics (mae/rmse/success_rate/stability_score/samples)
  - changePoints, outlierClassifications, trendForecast, populationPrior, benchmark, auditTrail
  - Backward compatibility (v1 core fields all still present)
  - Determinism on two identical calls (ignoring auditTrail.generated_at)
  - Cold-start cap by sufficiency level (1/2/3)
  - Outlier handling (logging-error 5d and missed-cycle ~90d) classified + excluded
  - Auth gating (401/403 without token)
  - Existing /dashboard, /daily-summary, /analytics still 200
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

from conftest import API, register_user  # noqa: E402


V1_CORE_KEYS = {
    "predictedDate", "earliestDate", "latestDate", "confidence", "regularity",
    "cycleLengthPrediction", "probabilityDistribution",
    "fertileWindowStart", "fertileWindowEnd", "ovulationDate",
    "healthFlags", "trendInsights", "profile",
}

V2_ADDED_KEYS = {
    "engineVersion", "algorithmVersion", "models", "finalPrediction",
    "modelWeights", "predictionErrors", "confidenceSource", "confidenceSamples",
    "reliabilityIndex", "predictionIntervals", "changePoints",
    "outlierClassifications", "dataSufficiency", "trendForecast",
    "validationMetrics", "populationPrior", "benchmark", "auditTrail",
}


# ----------------------------- Helpers -----------------------------
def _seed_cycles(client, headers, starts):
    for s in starts:
        r = client.post(f"{API}/cycles", json={"start_date": s},
                        headers=headers, timeout=20)
        assert r.status_code == 200, f"seed cycle {s} failed: {r.status_code} {r.text}"


def _seed_cycle_pairs(client, headers, pairs):
    """Seed cycles with explicit (start, end) pairs to feed period_length data."""
    for s, e in pairs:
        body = {"start_date": s}
        if e:
            body["end_date"] = e
        r = client.post(f"{API}/cycles", json=body, headers=headers, timeout=20)
        assert r.status_code == 200, f"seed pair {s}/{e} failed: {r.text}"


def _starts_with_deltas(deltas, anchor=None):
    """Build start dates oldest->newest from a list of gaps; the last start is `anchor`."""
    anchor = anchor or (date.today() - timedelta(days=2))
    total = sum(deltas)
    oldest = anchor - timedelta(days=total)
    cur = oldest
    out = [cur.isoformat()]
    for d in deltas:
        cur = cur + timedelta(days=d)
        out.append(cur.isoformat())
    return out  # len = len(deltas) + 1


# ============================== Auth gating ==============================
class TestAuthGating:
    def test_no_token(self, client):
        r = client.get(f"{API}/prediction", timeout=20)
        assert r.status_code in (401, 403), r.text

    def test_bad_token(self, client):
        r = client.get(f"{API}/prediction",
                       headers={"Authorization": "Bearer not-a-real-token"},
                       timeout=20)
        assert r.status_code in (401, 403), r.text


# ============================== Contract / v2 fields ==============================
class TestV2Contract:
    def test_v2_keys_present_no_cycles(self, client, auth_headers):
        r = client.get(f"{API}/prediction", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        missing_v1 = V1_CORE_KEYS - set(body.keys())
        missing_v2 = V2_ADDED_KEYS - set(body.keys())
        assert not missing_v1, f"missing v1 keys: {missing_v1}"
        assert not missing_v2, f"missing v2 keys: {missing_v2}"
        assert body["engineVersion"] in ("2.0.0", "3.0.0"), body["engineVersion"]
        assert body["algorithmVersion"] in ("ensemble-v1", "verified-forecast-v1")

    def test_v2_keys_with_history(self, client, auth_headers):
        # 12 regular 28-day cycles
        starts = _starts_with_deltas([28] * 11)
        _seed_cycles(client, auth_headers, starts)
        r = client.get(f"{API}/prediction", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()

        # ---- v1 core integrity ----
        assert body["predictedDate"], "predictedDate missing"
        assert body["earliestDate"] and body["latestDate"]
        assert isinstance(body["probabilityDistribution"], list)
        assert len(body["probabilityDistribution"]) == 14
        assert body["regularity"] in ("Very Regular", "Regular", "Moderately Irregular",
                                      "Highly Irregular", "Unknown")

        # ---- engineVersion ----
        assert body["engineVersion"] in ("2.0.0", "3.0.0")

        # ---- reliabilityIndex ----
        ri = body["reliabilityIndex"]
        assert isinstance(ri, dict)
        assert 0 <= ri["score"] <= 100, ri
        assert ri["classification"] in ("Excellent", "High", "Moderate", "Low", "Very Low"), ri
        assert set(ri["factors"].keys()) == {
            "number_of_cycles", "cycle_variability", "prediction_accuracy",
            "outlier_frequency", "missing_data_frequency"}

        # ---- predictionIntervals p50/p75/p90/p95 ----
        pi = body["predictionIntervals"]
        for lvl in ("p50", "p75", "p90", "p95"):
            assert lvl in pi, f"missing interval {lvl}: {pi}"
            assert "start" in pi[lvl] and "end" in pi[lvl] and "half_width_days" in pi[lvl]
        # Wider intervals should not be tighter than narrower ones.
        hw = [pi[f"p{p}"]["half_width_days"] for p in (50, 75, 90, 95)]
        assert hw == sorted(hw), f"intervals not monotonic: {hw}"
        assert pi.get("source") in ("empirical_error", "model_variance", "conformal",
                                    "empirical_error (conformal_rejected)",
                                    "model_variance (conformal_rejected)")

        # ---- dataSufficiency ----
        ds = body["dataSufficiency"]
        assert ds["level"] in (0, 1, 2, 3, 4), ds
        assert isinstance(ds["label"], str) and ds["label"]
        assert 0 <= ds["max_confidence"] <= 95
        assert ds["level"] == 4, "12 cycles should be max level 4"

        # ---- modelWeights ----
        mw = body["modelWeights"]
        assert set(mw.keys()) == {"weighted", "median", "bayesian", "trend", "error_corrected"}
        s = sum(mw.values())
        assert abs(s - 1.0) < 1e-3, f"weights sum {s} ≠ 1.0"
        for k, v in mw.items():
            assert v >= 0, f"{k} weight negative"
            assert v <= 0.40 + 1e-6, f"{k} weight {v} exceeds 0.40 cap"

        # ---- predictionErrors ----
        pe = body["predictionErrors"]
        assert set(pe.keys()) == {"rolling_3_cycle_error", "rolling_6_cycle_error",
                                  "rolling_12_cycle_error", "bias_days"}
        # With 12 same-length cycles + 28-day defaults, errors should be ~0.
        assert pe["bias_days"] is not None
        for k in ("rolling_3_cycle_error", "rolling_6_cycle_error", "rolling_12_cycle_error"):
            assert pe[k] is None or isinstance(pe[k], (int, float))

        # ---- validationMetrics ----
        vm = body["validationMetrics"]
        assert set(vm.keys()) >= {"mae", "rmse", "success_rate", "stability_score", "samples"}
        assert vm["samples"] >= 1
        assert 0 <= vm["success_rate"] <= 100

        # ---- changePoints / outlierClassifications / trendForecast ----
        assert isinstance(body["changePoints"], list)
        assert isinstance(body["outlierClassifications"], list)
        tf = body["trendForecast"]
        assert set(tf.keys()) >= {"cycle_length_strength", "variability_strength",
                                  "period_length_strength", "messages"}

        # ---- populationPrior ----
        pp = body["populationPrior"]
        assert set(pp.keys()) >= {"average_cycle_length", "average_period_length",
                                  "variance", "blend_weight"}
        assert 0.0 <= pp["blend_weight"] <= 1.0
        # 12 cycles >> 6, so blend_weight is clamped to 1.0
        assert pp["blend_weight"] == 1.0

        # ---- benchmark ----
        bm = body["benchmark"]
        assert set(bm.keys()) >= {"engine_version", "overall_accuracy", "mae", "rmse",
                                  "samples", "by_regularity", "by_cycle_count", "records"}
        assert bm["engine_version"] in ("2.0.0", "3.0.0")
        assert bm["by_cycle_count"] == 12
        assert isinstance(bm["records"], list)

        # ---- auditTrail ----
        at = body["auditTrail"]
        assert set(at.keys()) >= {
            "prediction_id", "generated_at", "contributing_cycles", "excluded_cycles",
            "outlier_adjustments", "trend_adjustments", "confidence_source", "model_versions"}
        assert at["model_versions"]["engine_version"] in ("2.0.0", "3.0.0")
        assert len(at["contributing_cycles"]) == 12


# ============================== Confidence cap by sufficiency ==============================
class TestSufficiencyCap:
    @pytest.mark.parametrize("n_cycles,expected_level,expected_max", [
        (1, 1, 30),
        (2, 2, 50),
        (4, 3, 75),
    ])
    def test_cold_start_levels(self, client, n_cycles, expected_level, expected_max):
        # Each test needs its own user — use the same register helper.
        user = register_user(client, prefix=f"v2cold{n_cycles}")
        headers = {"Authorization": f"Bearer {user['access_token']}",
                   "Content-Type": "application/json"}
        starts = _starts_with_deltas([28] * (n_cycles - 1)) if n_cycles > 1 else [
            (date.today() - timedelta(days=10)).isoformat()]
        _seed_cycles(client, headers, starts)

        r = client.get(f"{API}/prediction", headers=headers, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()

        ds = body["dataSufficiency"]
        assert ds["level"] == expected_level, ds
        assert ds["max_confidence"] == expected_max, ds
        assert body["confidence"] <= ds["max_confidence"], (
            f"confidence {body['confidence']} exceeds cap {ds['max_confidence']}")

        # populationPrior.blend_weight should be in [0, 1) for <6 cycles
        bw = body["populationPrior"]["blend_weight"]
        assert 0.0 <= bw < 1.0, bw


# ============================== Determinism ==============================
class TestDeterminism:
    def test_two_identical_calls_match(self, client, auth_headers):
        starts = _starts_with_deltas([28] * 8)
        _seed_cycles(client, auth_headers, starts)
        r1 = client.get(f"{API}/prediction?today=2025-06-01",
                        headers=auth_headers, timeout=20)
        r2 = client.get(f"{API}/prediction?today=2025-06-01",
                        headers=auth_headers, timeout=20)
        assert r1.status_code == r2.status_code == 200
        j1, j2 = r1.json(), r2.json()
        # auditTrail.generated_at is wall-clock metadata only — strip it.
        for j in (j1, j2):
            j.get("auditTrail", {}).pop("generated_at", None)
        assert j1 == j2, "non-deterministic v2 output"

        # auditTrail.prediction_id must be byte-identical (deterministic hash).
        assert j1["auditTrail"]["prediction_id"] == j2["auditTrail"]["prediction_id"]


# ============================== Outlier handling ==============================
class TestOutlierClassification:
    def test_logging_error_short(self, client):
        """A 5-day gap (cycle length 5) should be classified as 'Logging Error' (wf=0.05)
        and appear in auditTrail.excluded_cycles (wf <= 0.15)."""
        user = register_user(client, "v2outShort")
        headers = {"Authorization": f"Bearer {user['access_token']}",
                   "Content-Type": "application/json"}
        # Mostly-28 cycles with one 5-day gap injected in the middle.
        deltas = [28, 28, 28, 5, 28, 28, 28, 28]
        starts = _starts_with_deltas(deltas)
        _seed_cycles(client, headers, starts)

        r = client.get(f"{API}/prediction", headers=headers, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        outliers = body["outlierClassifications"]
        assert outliers, "expected outlierClassifications to be non-empty"
        types = {o["outlier_type"] for o in outliers}
        assert "Logging Error" in types, f"expected Logging Error in {types}"

        for o in outliers:
            assert 0 < o["weight_factor"] < 1, o
        # The 5-day cycle (wf 0.05) should be excluded in the audit trail.
        excluded = body["auditTrail"]["excluded_cycles"]
        assert any(o["outlier_type"] == "Logging Error" for o in excluded), excluded

    def test_missed_cycle_long(self, client):
        """A ~90-day gap should be classified as 'Missed Cycle' (wf=0.10) and excluded."""
        user = register_user(client, "v2outLong")
        headers = {"Authorization": f"Bearer {user['access_token']}",
                   "Content-Type": "application/json"}
        deltas = [28, 28, 28, 90, 28, 28, 28, 28]
        starts = _starts_with_deltas(deltas)
        _seed_cycles(client, headers, starts)

        r = client.get(f"{API}/prediction", headers=headers, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        outliers = body["outlierClassifications"]
        assert outliers, "expected outliers"
        types = {o["outlier_type"] for o in outliers}
        assert "Missed Cycle" in types, f"expected Missed Cycle in {types}"
        excluded = body["auditTrail"]["excluded_cycles"]
        assert any(o["outlier_type"] == "Missed Cycle" for o in excluded), excluded


# ============================== Regression smoke ==============================
class TestExistingFlows:
    def test_dashboard(self, client, auth_headers):
        r = client.get(f"{API}/dashboard", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        assert "prediction" in r.json()

    def test_daily_summary(self, client, auth_headers):
        r = client.get(f"{API}/daily-summary", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text

    def test_analytics(self, client, auth_headers):
        r = client.get(f"{API}/analytics", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("avg_cycle_length", "avg_period_length", "cycles_tracked"):
            assert k in body, f"missing analytics key {k}"
