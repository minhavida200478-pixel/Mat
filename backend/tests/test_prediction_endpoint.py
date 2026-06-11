"""Live API tests for the new MAT prediction engine endpoint: GET /api/prediction.

Covers: auth gating, response contract, empty/single-cycle behavior, regular history
prediction quality, outlier resilience, ?today= parameter, determinism, and a quick
regression smoke of pre-existing endpoints (health, login, cycles CRUD, dashboard,
analytics).
"""
import os
from datetime import date, timedelta

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
import requests  # noqa: E402

from conftest import API, register_user  # noqa: E402


# ----------------------------- Small helpers -----------------------------
def _seed_cycles(client, headers, starts):
    """POST /api/cycles for each YYYY-MM-DD start date. Returns created ids."""
    ids = []
    for s in starts:
        r = client.post(f"{API}/cycles", json={"start_date": s}, headers=headers, timeout=20)
        assert r.status_code == 200, f"seed cycle {s} failed: {r.status_code} {r.text}"
        ids.append(r.json()["id"])
    return ids


def _regular_cycle_starts(n: int, length: int = 28, anchor: date | None = None):
    """Return n start dates `length` days apart, ending shortly before `anchor`."""
    anchor = anchor or (date.today() - timedelta(days=2))
    # anchor is the most-recent start
    return [(anchor - timedelta(days=length * (n - 1 - i))).isoformat() for i in range(n)]


# ----------------------------- Auth gating -----------------------------
class TestPredictionAuth:
    def test_requires_auth_no_token(self, client):
        r = client.get(f"{API}/prediction", timeout=20)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}: {r.text}"

    def test_requires_auth_bad_token(self, client):
        r = client.get(f"{API}/prediction",
                       headers={"Authorization": "Bearer not-a-real-token"}, timeout=20)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}: {r.text}"


# ----------------------------- Response contract -----------------------------
EXPECTED_KEYS = {"predictedDate", "earliestDate", "latestDate", "confidence",
                 "regularity", "cycleLengthPrediction", "probabilityDistribution",
                 "healthFlags", "trendInsights", "profile"}


class TestPredictionContract:
    def test_response_keys_no_cycles(self, client, auth_headers):
        r = client.get(f"{API}/prediction", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        missing = EXPECTED_KEYS - set(body.keys())
        assert not missing, f"missing keys: {missing}"

    def test_empty_user_defaults(self, client, auth_headers):
        r = client.get(f"{API}/prediction", headers=auth_headers, timeout=20)
        body = r.json()
        assert body["predictedDate"] is None
        assert body["earliestDate"] is None
        assert body["latestDate"] is None
        assert body["regularity"] == "Unknown"
        assert body["cycleLengthPrediction"] == 28
        assert body["probabilityDistribution"] == []
        assert body["profile"]["cycle_count"] == 0


# ----------------------------- Single-cycle behavior -----------------------------
class TestSingleCycle:
    def test_single_cycle_predicts_28_days_later(self, client, auth_headers):
        start = (date.today() - timedelta(days=10)).isoformat()
        _seed_cycles(client, client, []) if False else None  # noqa - placeholder
        r = client.post(f"{API}/cycles", json={"start_date": start},
                        headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text

        pr = client.get(f"{API}/prediction", headers=auth_headers, timeout=20)
        assert pr.status_code == 200, pr.text
        body = pr.json()
        expected = (date.fromisoformat(start) + timedelta(days=28)).isoformat()
        assert body["predictedDate"] == expected
        assert body["regularity"] == "Unknown"  # <3 cycles
        assert body["cycleLengthPrediction"] == 28
        assert body["profile"]["cycle_count"] == 1


# ----------------------------- 12 regular cycles -----------------------------
class TestRegularHistory:
    def test_twelve_regular_cycles(self, client, auth_headers):
        anchor = date.today() - timedelta(days=2)
        starts = _regular_cycle_starts(12, 28, anchor=anchor)
        _seed_cycles(client, auth_headers, starts)

        r = client.get(f"{API}/prediction", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()

        assert body["regularity"] in ("Very Regular", "Regular"), body["regularity"]
        assert body["confidence"] >= 60, f"low confidence: {body['confidence']}"
        assert len(body["probabilityDistribution"]) == 14, len(body["probabilityDistribution"])

        # peak at dayOffset 0
        peak = max(body["probabilityDistribution"], key=lambda d: d["probability"])
        assert peak["dayOffset"] == 0, peak

        # earliest < predicted < latest
        pd = date.fromisoformat(body["predictedDate"])
        ed = date.fromisoformat(body["earliestDate"])
        ld = date.fromisoformat(body["latestDate"])
        assert ed < pd < ld, (ed, pd, ld)

        # cycle length prediction near 28
        assert 26 <= body["cycleLengthPrediction"] <= 30
        assert body["profile"]["cycle_count"] == 12


# ----------------------------- Outlier resilience -----------------------------
class TestOutlier:
    def test_outlier_does_not_corrupt_prediction(self, client, auth_headers):
        # Build mostly-regular 28-day history with one ~95-day gap injected in the middle.
        anchor = date.today() - timedelta(days=2)
        starts = []
        cur = anchor
        # We will create 10 cycles oldest-first. One gap is 95 days; rest are 28.
        # Build deltas list, walk forward from oldest.
        deltas = [28, 28, 28, 95, 28, 28, 28, 28, 28]  # 9 gaps -> 10 cycles
        oldest = anchor - timedelta(days=sum(deltas))
        cur = oldest
        starts.append(cur.isoformat())
        for d in deltas:
            cur = cur + timedelta(days=d)
            starts.append(cur.isoformat())

        _seed_cycles(client, auth_headers, starts)
        r = client.get(f"{API}/prediction", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()

        clp = body["cycleLengthPrediction"]
        assert 24 <= clp <= 32, f"outlier corrupted prediction: clp={clp}"
        assert body["profile"]["outlier_count"] >= 1, body["profile"]


# ----------------------------- ?today= parameter -----------------------------
class TestTodayParam:
    def test_today_query_param_accepted(self, client, auth_headers):
        # Seed a single cycle, then call with explicit today date.
        start = "2025-01-01"
        client.post(f"{API}/cycles", json={"start_date": start},
                    headers=auth_headers, timeout=20)
        r = client.get(f"{API}/prediction?today=2025-02-15",
                       headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        # predicted date is last_start + cycleLengthPrediction, independent of today
        # but the call must succeed and contract must hold.
        assert body["predictedDate"] == "2025-01-29"
        assert set(EXPECTED_KEYS).issubset(body.keys())


# ----------------------------- Determinism -----------------------------
class TestDeterminism:
    def test_two_identical_calls_match(self, client, auth_headers):
        anchor = date.today() - timedelta(days=2)
        starts = _regular_cycle_starts(6, 28, anchor=anchor)
        _seed_cycles(client, auth_headers, starts)
        r1 = client.get(f"{API}/prediction?today=2025-06-01",
                        headers=auth_headers, timeout=20)
        r2 = client.get(f"{API}/prediction?today=2025-06-01",
                        headers=auth_headers, timeout=20)
        assert r1.status_code == r2.status_code == 200
        # generated_at in the audit trail is wall-clock metadata (not a prediction
        # value); every prediction value must otherwise be byte-identical (P18).
        j1, j2 = r1.json(), r2.json()
        for j in (j1, j2):
            j.get("auditTrail", {}).pop("generated_at", None)
        assert j1 == j2, "non-deterministic output"


# ----------------------------- Regression smoke -----------------------------
class TestRegressionSmoke:
    def test_health(self, client):
        r = client.get(f"{API}/health", timeout=20)
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_demo_login(self, client):
        r = client.post(f"{API}/auth/login",
                        json={"email": "demo@cycle.app", "password": "DemoPass123!"},
                        timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "access_token" in body and "refresh_token" in body

    def test_cycles_crud(self, client, auth_headers):
        start = (date.today() - timedelta(days=40)).isoformat()
        r = client.post(f"{API}/cycles", json={"start_date": start},
                        headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        cid = r.json()["id"]

        r = client.get(f"{API}/cycles", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        assert any(c["id"] == cid for c in r.json())

        new_end = (date.fromisoformat(start) + timedelta(days=5)).isoformat()
        r = client.put(f"{API}/cycles/{cid}", json={"end_date": new_end},
                       headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text

        r = client.delete(f"{API}/cycles/{cid}", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text

    def test_dashboard_and_analytics(self, client, auth_headers):
        r = client.get(f"{API}/dashboard", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        assert "prediction" in r.json()
        r = client.get(f"{API}/analytics", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("avg_cycle_length", "avg_period_length", "cycles_tracked"):
            assert k in body
