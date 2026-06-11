"""API tests for the v3 verified-forecasting engine endpoints."""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from conftest import API  # noqa: E402


def seed_cycles(client, headers, lengths, first=date(2025, 1, 6)):
    start = first
    for L in lengths:
        r = client.post(f"{API}/cycles", headers=headers, json={
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=4)).isoformat(),
        }, timeout=20)
        assert r.status_code == 200, r.text
        start += timedelta(days=L)


class TestPredictionV3Endpoint:
    def test_prediction_returns_v3_fields(self, client, auth_headers):
        seed_cycles(client, auth_headers, [28, 27, 30, 28, 29, 26, 31, 28, 27, 29])
        r = client.get(f"{API}/prediction", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        p = r.json()
        assert p["engineVersion"] == "3.0.0"
        assert p["algorithmVersion"] == "verified-forecast-v1"
        for key in ("errorLearning", "modelAccuracy", "modelWeightHistory",
                    "lookback", "activeForecastingStrategy", "conformalCalibration",
                    "quantileForecast", "forecastStability", "calibration",
                    "deploymentGate"):
            assert key in p, f"missing {key}"
        # v2 / UI compatibility
        for key in ("predictedDate", "confidence", "reliabilityIndex",
                    "predictionIntervals", "dataSufficiency", "probabilityDistribution"):
            assert key in p
        assert p["activeForecastingStrategy"] in (
            "weighted", "median", "bayesian", "trend", "error_corrected", "ensemble")
        assert p["lookback"]["optimal_window"] in (3, 6, 12, 24)

    def test_history_row_carries_v3_fields(self, client, auth_headers):
        seed_cycles(client, auth_headers, [28, 29, 27, 28, 30, 28, 27, 29])
        client.get(f"{API}/prediction", headers=auth_headers, timeout=30)
        r = client.get(f"{API}/prediction/history", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        rows = r.json()["history"]
        assert rows
        row = rows[0]
        for key in ("active_strategy", "optimal_window", "model_accuracy",
                    "stability_score", "quantile_method"):
            assert key in row, f"missing persisted field {key}"
        assert row["engine_version"] == "3.0.0"


class TestMonitoringEndpoint:
    def test_requires_auth(self, client):
        r = client.get(f"{API}/prediction/monitoring", timeout=20)
        assert r.status_code in (401, 403)

    def test_monitoring_windows(self, client, auth_headers):
        seed_cycles(client, auth_headers, [28, 27, 30, 28, 29, 26, 31, 28, 27, 29],
                    first=date.today() - timedelta(days=290))
        client.get(f"{API}/prediction", headers=auth_headers, timeout=30)
        r = client.get(f"{API}/prediction/monitoring", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert body["engine_version"] == "3.0.0"
        for w in ("30_day", "90_day", "365_day", "lifetime"):
            assert w in body["windows"]
            m = body["windows"][w]
            for k in ("samples", "mae", "rmse", "median_error", "calibration_error",
                      "p95_error", "coverage", "coverage_error"):
                assert k in m
        life = body["windows"]["lifetime"]
        assert life["samples"] > 0
        assert life["mae"] is not None and life["mae"] >= 0
        assert life["rmse"] >= life["mae"]

    def test_monitoring_empty_user(self, client, auth_headers):
        r = client.get(f"{API}/prediction/monitoring", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        assert r.json()["windows"]["lifetime"]["samples"] == 0
