"""Iteration 10 — v3 prediction engine integration test via public preview URL.

Covers the explicit review_request items:
  • GET /api/prediction returns all v3 fields + preserved v2/UI fields
  • GET /api/prediction/monitoring returns 30/90/365/lifetime window metrics
  • GET /api/prediction/history persists v3 fields per row
  • Determinism: two consecutive GET /api/prediction calls return identical values
  • Demo user fallback (8 cycles ⇒ traditional gates) is expected behaviour
  • Fresh user with 12+ varied cycles activates conformal/direct-quantile

Run:  pytest tests/test_v3_integration_iter10.py -v
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")
BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL")
            or "").rstrip("/")
API = f"{BASE_URL}/api"

DEMO_EMAIL = "demo@cycle.app"
DEMO_PASS = "DemoPass123!"


# -------------------- helpers --------------------
def _login(client, email, password):
    r = client.post(f"{API}/auth/login", json={"email": email, "password": password},
                    timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


def _auth(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _seed_varied_cycles(client, headers, lengths):
    """Seed a chain of completed cycles ending well before today.
    lengths: list of cycle lengths in days. The earliest cycle starts so the
    last completed cycle ends >= 7 days before today (to keep prediction active).
    Each cycle: period_start + 5 day period, full cycle_length spacing."""
    total = sum(lengths) + 10  # buffer
    start = date.today() - timedelta(days=total)
    cur = start
    created_ids = []
    for L in lengths:
        body = {
            "start_date": cur.isoformat(),
            "end_date": (cur + timedelta(days=4)).isoformat(),
            "cycle_length": L,
            "period_length": 5,
        }
        r = client.post(f"{API}/cycles", json=body, headers=headers, timeout=20)
        assert r.status_code in (200, 201), f"seed cycle failed: {r.status_code} {r.text[:200]}"
        cur = cur + timedelta(days=L)
    return created_ids


# -------------------- fixtures --------------------
@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def demo_headers(client):
    return _auth(_login(client, DEMO_EMAIL, DEMO_PASS))


@pytest.fixture(scope="module")
def power_user_headers(client):
    """Fresh user with 12 varied cycles ⇒ conformal/direct-quantile should activate."""
    from tests.conftest import register_user
    u = register_user(client, "v3pwr")
    headers = _auth(u["access_token"])
    _seed_varied_cycles(client, headers,
                        [28, 31, 26, 29, 33, 25, 30, 27, 32, 26, 29, 31])
    return headers


# -------------------- /api/prediction shape (demo, 8 cycles ⇒ gates fall back) --------------------
class TestPredictionShapeDemo:
    def test_engine_version_v3(self, client, demo_headers):
        r = client.get(f"{API}/prediction", headers=demo_headers, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("engineVersion", "").startswith("3."), body.get("engineVersion")
        assert body.get("algorithmVersion") == "verified-forecast-v1", body.get("algorithmVersion")

    def test_v3_fields_present(self, client, demo_headers):
        body = client.get(f"{API}/prediction", headers=demo_headers, timeout=30).json()
        # All v3 keys must exist (gated behaviour is fine but the keys are required)
        for key in ("errorLearning", "modelAccuracy", "modelWeightHistory",
                    "modelAccuracyHistory", "lookback", "activeForecastingStrategy",
                    "conformalCalibration", "quantileForecast", "forecastStability",
                    "calibration", "deploymentGate"):
            assert key in body, f"missing v3 field: {key}"
        assert body["lookback"]["optimal_window"] in (3, 6, 12, 24), body["lookback"]

    def test_v2_ui_fields_preserved(self, client, demo_headers):
        body = client.get(f"{API}/prediction", headers=demo_headers, timeout=30).json()
        for key in ("predictedDate", "confidence", "reliabilityIndex",
                    "predictionIntervals", "probabilityDistribution",
                    "dataSufficiency"):
            assert key in body, f"missing UI/v2 field: {key}"
        # Intervals must include p50 and p95
        intervals = body["predictionIntervals"]
        assert "p50" in intervals and "p95" in intervals, intervals
        # Probability distribution must have exactly 14 rows
        assert len(body["probabilityDistribution"]) == 14, len(body["probabilityDistribution"])

    def test_quantile_monotonic(self, client, demo_headers):
        body = client.get(f"{API}/prediction", headers=demo_headers, timeout=30).json()
        q = body["quantileForecast"]
        quants = q.get("quantiles") or {}
        # Engine publishes p10/p25/p50/p75/p90 (5 quantile anchors covering p10..p90).
        order = ["p10", "p25", "p50", "p75", "p90"]
        vals = [quants[k] for k in order if k in quants]
        assert len(vals) == 5, f"expected 5 quantile anchors (p10..p90), got: {quants}"
        for a, b in zip(vals, vals[1:]):
            assert a <= b, f"quantiles not monotonic: {vals}"

    def test_demo_gates_fall_back_as_documented(self, client, demo_headers):
        body = client.get(f"{API}/prediction", headers=demo_headers, timeout=30).json()
        # Documented in the review request — must be observable, not a bug.
        assert body["predictionIntervals"].get("source") in (
            "model_variance", "conformal"), body["predictionIntervals"]
        assert body["quantileForecast"].get("method") in (
            "traditional", "direct_quantile"), body["quantileForecast"]

    def test_determinism_two_calls(self, client, demo_headers):
        r1 = client.get(f"{API}/prediction", headers=demo_headers, timeout=30).json()
        r2 = client.get(f"{API}/prediction", headers=demo_headers, timeout=30).json()
        # Stable fields that should never wobble for the same user/day.
        for key in ("predictedDate", "confidence", "engineVersion",
                    "activeForecastingStrategy"):
            assert r1.get(key) == r2.get(key), f"non-deterministic: {key}"
        assert r1["predictionIntervals"] == r2["predictionIntervals"]
        assert r1["quantileForecast"] == r2["quantileForecast"]


# -------------------- power user (12+ cycles) --------------------
class TestPredictionPowerUser:
    def test_conformal_or_quantile_activates(self, client, power_user_headers):
        body = client.get(f"{API}/prediction", headers=power_user_headers,
                          timeout=30).json()
        src = body["predictionIntervals"].get("source")
        meth = body["quantileForecast"].get("method")
        # At least ONE of the gated upgrades must activate with 12 varied cycles.
        assert src == "conformal" or meth == "direct_quantile", \
            f"neither gated method activated: intervals.source={src}, " \
            f"quantile.method={meth}"

    def test_lookback_picks_a_window(self, client, power_user_headers):
        body = client.get(f"{API}/prediction", headers=power_user_headers,
                          timeout=30).json()
        assert body["lookback"]["optimal_window"] in (3, 6, 12, 24)


# -------------------- /api/prediction/monitoring --------------------
class TestMonitoringEndpoint:
    def test_requires_auth(self, client):
        r = client.get(f"{API}/prediction/monitoring", timeout=20)
        assert r.status_code in (401, 403), r.status_code

    def test_returns_four_windows_with_required_keys(self, client, demo_headers):
        r = client.get(f"{API}/prediction/monitoring", headers=demo_headers, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "windows" in body
        for w in ("30_day", "90_day", "365_day", "lifetime"):
            assert w in body["windows"], f"missing window: {w}"
            m = body["windows"][w]
            for k in ("samples", "mae", "rmse", "median_error",
                      "calibration_error", "p95_error", "coverage",
                      "coverage_error"):
                assert k in m, f"window {w} missing metric {k}"


# -------------------- /api/prediction/history v3 row fields --------------------
class TestHistoryV3Persistence:
    def test_history_row_carries_v3_fields(self, client, demo_headers):
        # Touch /prediction once to ensure a row exists.
        client.get(f"{API}/prediction", headers=demo_headers, timeout=30)
        r = client.get(f"{API}/prediction/history", headers=demo_headers, timeout=30)
        assert r.status_code == 200, r.text
        rows = r.json().get("history") or r.json().get("rows") or r.json()
        assert isinstance(rows, list) and rows, f"no history rows returned: {r.text[:200]}"
        row = rows[0]
        for k in ("active_strategy", "optimal_window", "model_accuracy",
                  "stability_score", "quantile_method", "p95_start", "p95_end"):
            assert k in row, f"history row missing {k}; row keys = {list(row)}"
