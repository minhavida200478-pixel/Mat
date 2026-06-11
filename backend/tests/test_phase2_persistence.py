"""Phase 2 persistence layer tests (P2 / P11 / P14 spec gaps).

Covers the three storage requirements added on top of the computed-only engine:
  P2  prediction_history rows carry prediction_date + last_cycle_start and are
      auto-resolved with actual_period_start / prediction_error_days once the
      next period is logged.
  P11 monthly validation snapshots (one per user+month) exposed via
      GET /api/prediction/history -> monthlySnapshots.
  P14 persisted benchmark/validation table (db.benchmark_records) with one row
      per walk-forward (predicted, actual) pair.
"""
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from dotenv import load_dotenv
from pymongo import MongoClient

from .conftest import API, register_user

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

CYCLES = [
    ("2025-11-14", "2025-11-18"),
    ("2025-12-12", "2025-12-16"),
    ("2026-01-10", "2026-01-14"),
    ("2026-02-06", "2026-02-10"),
    ("2026-03-07", "2026-03-11"),
    ("2026-04-04", "2026-04-08"),
    ("2026-05-03", "2026-05-07"),
]
NEXT_CYCLE = ("2026-05-31", "2026-06-04")


@pytest.fixture(scope="module")
def mongo():
    client = MongoClient(os.environ["MONGO_URL"])
    yield client[os.environ["DB_NAME"]]
    client.close()


@pytest.fixture(scope="module")
def seeded(mongo):
    """One user with 7 cycles + a prediction, then an 8th cycle + new prediction."""
    import requests
    client = requests.Session()
    client.headers.update({"Content-Type": "application/json"})
    user = register_user(client, "phase2")
    h = {"Authorization": f"Bearer {user['access_token']}"}

    for sd, ed in CYCLES:
        r = client.post(f"{API}/cycles", json={"start_date": sd, "end_date": ed},
                        headers=h, timeout=20)
        assert r.status_code == 200, r.text
    first = client.get(f"{API}/prediction", headers=h, timeout=20)
    assert first.status_code == 200

    sd, ed = NEXT_CYCLE
    r = client.post(f"{API}/cycles", json={"start_date": sd, "end_date": ed},
                    headers=h, timeout=20)
    assert r.status_code == 200
    second = client.get(f"{API}/prediction", headers=h, timeout=20)
    assert second.status_code == 200

    hist = client.get(f"{API}/prediction/history?limit=50", headers=h, timeout=20)
    assert hist.status_code == 200

    me = client.get(f"{API}/auth/me", headers=h, timeout=20)
    return {
        "user_id": me.json()["id"],
        "first_prediction": first.json(),
        "second_prediction": second.json(),
        "history": hist.json(),
    }


# ----------------------------- P2: error learning rows -----------------------------
class TestPredictionHistoryResolution:
    def test_rows_carry_p2_fields(self, seeded):
        rows = seeded["history"]["history"]
        assert len(rows) >= 2
        for r in rows:
            assert "prediction_date" in r
            assert "last_cycle_start" in r
            assert "actual_period_start" in r
            assert "prediction_error_days" in r
            assert r["model_weights"]  # P13: weights stored per prediction
            assert r["engine_version"] in ("2.0.0", "3.0.0")

    def test_prior_prediction_resolved_with_actual(self, seeded):
        rows = seeded["history"]["history"]
        resolved = [r for r in rows if r["actual_period_start"] is not None]
        assert resolved, "older prediction must be resolved once next cycle logged"
        row = resolved[0]
        assert row["actual_period_start"] == NEXT_CYCLE[0]
        predicted = datetime.strptime(row["predicted_period_start"], "%Y-%m-%d")
        actual = datetime.strptime(row["actual_period_start"], "%Y-%m-%d")
        assert row["prediction_error_days"] == (actual - predicted).days
        assert row["last_cycle_start"] == CYCLES[-1][0]

    def test_latest_prediction_still_unresolved(self, seeded):
        rows = seeded["history"]["history"]  # newest first
        assert rows[0]["actual_period_start"] is None
        assert rows[0]["prediction_error_days"] is None
        assert rows[0]["last_cycle_start"] == NEXT_CYCLE[0]


# ----------------------------- P11: monthly snapshots -----------------------------
class TestMonthlySnapshots:
    def test_snapshot_exposed_in_history_endpoint(self, seeded):
        snaps = seeded["history"]["monthlySnapshots"]
        assert len(snaps) >= 1
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")
        assert snaps[0]["month"] == current_month

    def test_snapshot_contains_metrics(self, seeded):
        s = seeded["history"]["monthlySnapshots"][0]
        m = s["metrics"]
        for key in ("mae", "rmse", "success_rate", "stability_score", "samples"):
            assert key in m
        assert m["samples"] >= 1
        assert s["engine_version"] in ("2.0.0", "3.0.0")

    def test_one_snapshot_per_month_idempotent(self, seeded, mongo):
        count = mongo.validation_snapshots.count_documents(
            {"user_id": seeded["user_id"]})
        assert count == 1  # two /prediction calls, same month -> one row


# ----------------------------- P14: benchmark table -----------------------------
class TestBenchmarkRecords:
    def test_records_persisted(self, seeded, mongo):
        recs = list(mongo.benchmark_records.find({"user_id": seeded["user_id"]}))
        # walk-forward starts after MIN_HISTORY=3 prior lengths; 7 lengths -> 4 records
        assert len(recs) >= 3

    def test_record_schema(self, seeded, mongo):
        rec = mongo.benchmark_records.find_one({"user_id": seeded["user_id"]})
        for key in ("prediction_date", "predicted_period_start",
                    "actual_period_start", "error_days", "confidence",
                    "engine_version", "regularity", "cycle_count"):
            assert key in rec, f"missing {key}"
        assert rec["engine_version"] in ("2.0.0", "3.0.0")
        assert isinstance(rec["error_days"], int)

    def test_records_idempotent_per_actual_date(self, seeded, mongo):
        pipeline = [
            {"$match": {"user_id": seeded["user_id"]}},
            {"$group": {"_id": "$actual_period_start", "n": {"$sum": 1}}},
            {"$match": {"n": {"$gt": 1}}},
        ]
        dupes = list(mongo.benchmark_records.aggregate(pipeline))
        assert dupes == []


# ----------------------------- regression: response untouched -----------------------------
class TestResponseRegression:
    def test_prediction_response_core_fields(self, seeded):
        p = seeded["second_prediction"]
        for key in ("predictedDate", "confidence", "reliabilityIndex",
                    "predictionIntervals", "modelWeights", "auditTrail",
                    "validationMetrics", "benchmark", "dataSufficiency"):
            assert key in p
        assert p["predictedDate"] is not None

    def test_history_endpoint_backward_compatible(self, seeded):
        d = seeded["history"]
        assert set(d) >= {"history", "count", "validationMetrics", "monthlySnapshots"}
        assert d["validationMetrics"]["metrics"]["samples"] >= 1
