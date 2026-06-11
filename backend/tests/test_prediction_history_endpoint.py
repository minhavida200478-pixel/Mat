"""Phase 2 P2 — GET /api/prediction/history live API tests.

Covers:
  * Auth gating (401/403 without/with bad token)
  * After GET /api/prediction, /api/prediction/history returns >=1 row with
    full schema (prediction_id, predicted_period_start, cycle_length_prediction,
    confidence, reliability_score, reliability_classification,
    data_sufficiency_level, model_weights, engine_version, generated_at,
    updated_at) and validationMetrics.metrics has {mae, rmse, success_rate,
    stability_score, samples}
  * Idempotency: repeated identical /api/prediction calls do NOT grow history.count
  * `limit` query parameter respected
  * outlierClassifications entries surface BOTH 'type' and 'outlier_type'
    keys with the same value
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

from conftest import API, register_user  # noqa: E402


REQUIRED_HISTORY_KEYS = {
    "prediction_id",
    "predicted_period_start",
    "cycle_length_prediction",
    "confidence",
    "reliability_score",
    "reliability_classification",
    "data_sufficiency_level",
    "model_weights",
    "engine_version",
    "generated_at",
    "updated_at",
}

REQUIRED_VM_KEYS = {"mae", "rmse", "success_rate", "stability_score", "samples"}


def _seed_cycles(client, headers, starts):
    for s in starts:
        r = client.post(f"{API}/cycles", json={"start_date": s},
                        headers=headers, timeout=20)
        assert r.status_code == 200, f"seed {s} failed: {r.status_code} {r.text}"


def _starts_with_deltas(deltas, anchor=None):
    anchor = anchor or (date.today() - timedelta(days=2))
    total = sum(deltas)
    oldest = anchor - timedelta(days=total)
    cur = oldest
    out = [cur.isoformat()]
    for d in deltas:
        cur += timedelta(days=d)
        out.append(cur.isoformat())
    return out


# ============================== Auth gating ==============================
class TestHistoryAuth:
    def test_no_token(self, client):
        r = client.get(f"{API}/prediction/history", timeout=20)
        assert r.status_code in (401, 403), r.text

    def test_bad_token(self, client):
        r = client.get(
            f"{API}/prediction/history",
            headers={"Authorization": "Bearer not-a-real-token"},
            timeout=20,
        )
        assert r.status_code in (401, 403), r.text


# ============================== Contract ==============================
class TestHistoryContract:
    def test_history_populated_after_prediction(self, client, auth_headers):
        starts = _starts_with_deltas([28] * 9)
        _seed_cycles(client, auth_headers, starts)
        # Force a prediction so persistence happens
        rp = client.get(f"{API}/prediction", headers=auth_headers, timeout=20)
        assert rp.status_code == 200, rp.text

        rh = client.get(f"{API}/prediction/history",
                        headers=auth_headers, timeout=20)
        assert rh.status_code == 200, rh.text
        body = rh.json()

        # top-level shape
        assert set(body.keys()) >= {"history", "count", "validationMetrics"}, body.keys()
        assert isinstance(body["history"], list)
        assert body["count"] >= 1, body
        assert body["count"] == len(body["history"])

        row = body["history"][0]
        missing = REQUIRED_HISTORY_KEYS - set(row.keys())
        assert not missing, f"history row missing keys: {missing}; got {list(row.keys())}"

        # value sanity
        assert row["engine_version"] in ("2.0.0", "3.0.0"), row
        assert row["prediction_id"], row
        assert isinstance(row["model_weights"], dict)
        assert row["reliability_classification"] in (
            "Excellent", "High", "Moderate", "Low", "Very Low")

        # validationMetrics shape
        vm = body["validationMetrics"]
        assert vm is not None, "validationMetrics missing"
        assert "metrics" in vm, vm
        assert set(vm["metrics"].keys()) >= REQUIRED_VM_KEYS, vm["metrics"]

    def test_history_idempotent_on_repeated_prediction(self, client, auth_headers):
        starts = _starts_with_deltas([28] * 6)
        _seed_cycles(client, auth_headers, starts)

        # Pin `today` so prediction_id is byte-stable.
        url = f"{API}/prediction?today=2025-06-01"
        for _ in range(3):
            assert client.get(url, headers=auth_headers, timeout=20).status_code == 200

        rh1 = client.get(f"{API}/prediction/history",
                         headers=auth_headers, timeout=20).json()
        c1 = rh1["count"]

        # Call /api/prediction a few more times — count must NOT change.
        for _ in range(3):
            assert client.get(url, headers=auth_headers, timeout=20).status_code == 200

        rh2 = client.get(f"{API}/prediction/history",
                         headers=auth_headers, timeout=20).json()
        assert rh2["count"] == c1, (
            f"history count drifted across identical calls: {c1} -> {rh2['count']}; "
            f"prediction_ids={[r['prediction_id'] for r in rh2['history']]}"
        )

    def test_history_respects_limit(self, client, auth_headers):
        # prediction_id is derived from the cycle history only (engine_v2
        # _prediction_id hashes starts/ends, not `today`). To create two
        # distinct history rows we call /api/prediction, add a new cycle,
        # then call /api/prediction again.
        starts = _starts_with_deltas([28] * 6)
        _seed_cycles(client, auth_headers, starts)
        r = client.get(f"{API}/prediction", headers=auth_headers, timeout=20)
        assert r.status_code == 200

        new_start = (date.today() + timedelta(days=20)).isoformat()
        r2 = client.post(f"{API}/cycles", json={"start_date": new_start},
                         headers=auth_headers, timeout=20)
        assert r2.status_code == 200, r2.text
        r3 = client.get(f"{API}/prediction", headers=auth_headers, timeout=20)
        assert r3.status_code == 200

        full = client.get(f"{API}/prediction/history",
                         headers=auth_headers, timeout=20).json()
        assert full["count"] >= 2, full

        limited = client.get(f"{API}/prediction/history?limit=1",
                             headers=auth_headers, timeout=20).json()
        assert limited["count"] == 1, limited
        assert len(limited["history"]) == 1


# ============================== Regression: /api/prediction outlier alias ==
class TestOutlierTypeAlias:
    def test_outlier_entries_have_both_type_and_outlier_type(self, client):
        user = register_user(client, "v2outAlias")
        headers = {
            "Authorization": f"Bearer {user['access_token']}",
            "Content-Type": "application/json",
        }
        # 5-day gap to guarantee at least one Logging Error classification
        deltas = [28, 28, 28, 5, 28, 28, 28, 28]
        starts = _starts_with_deltas(deltas)
        _seed_cycles(client, headers, starts)

        r = client.get(f"{API}/prediction", headers=headers, timeout=20)
        assert r.status_code == 200, r.text
        outliers = r.json().get("outlierClassifications") or []
        assert outliers, "expected at least one outlier classification"
        for o in outliers:
            assert "type" in o, f"missing 'type' alias: {o}"
            assert "outlier_type" in o, f"missing 'outlier_type': {o}"
            assert o["type"] == o["outlier_type"], (
                f"type/outlier_type mismatch: {o}"
            )


# ============================== Regression smoke ==============================
class TestExistingFlowsStillGreen:
    def test_prediction_endpoint_200(self, client, auth_headers):
        r = client.get(f"{API}/prediction", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["engineVersion"] in ("2.0.0", "3.0.0")

    def test_dashboard(self, client, auth_headers):
        r = client.get(f"{API}/dashboard", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text

    def test_daily_summary(self, client, auth_headers):
        r = client.get(f"{API}/daily-summary", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text

    def test_analytics(self, client, auth_headers):
        r = client.get(f"{API}/analytics", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
