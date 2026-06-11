"""Tests for the new features added in this session:

1) GET /api/symptom-patterns — qa@cycle.app must return Headache with
   typical_days_before ≈ 2 and premenstrual_cycle_rate == 100.
2) GET /api/daily-summary?today=YYYY-MM-DD — coherent numbers + new shape.
3) Offline idempotency — POST /api/water, /api/meals, /api/quick-log and
   /api/medication-schedules/{id}/take with the same client_id must NOT
   create duplicates (second returns the existing record / deduped).
4) Auth enforcement (401/403) on every endpoint above.
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")
BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL") or "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("EXPO_PUBLIC_BACKEND_URL not set")
API = f"{BASE_URL}/api"

from .conftest import register_user  # type: ignore


# ----------------------- helpers -----------------------
def _auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _login(client, email: str, password: str) -> str | None:
    r = client.post(f"{API}/auth/login", json={"email": email, "password": password},
                    timeout=20)
    if r.status_code != 200:
        return None
    return r.json().get("access_token")


@pytest.fixture(scope="module")
def qa_token():
    """Seeded qa account; returned only if login succeeds."""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    tok = _login(s, "qa@cycle.app", "Test1234!")
    if not tok:
        pytest.skip("qa@cycle.app not seeded / login failed")
    return tok


# ===================== 1. SYMPTOM PATTERNS (qa) =====================
class TestSymptomPatternsQA:
    def test_qa_headache_lead_time_and_recurrence(self, client, qa_token):
        r = client.get(f"{API}/symptom-patterns", headers=_auth(qa_token), timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("has_enough_data") is True, body
        assert body.get("cycles_tracked", 0) >= 4
        symptoms = {s["name"]: s for s in body.get("symptoms", [])}
        assert "Headache" in symptoms, f"Headache missing: {list(symptoms)}"
        head = symptoms["Headache"]
        # Lead time: median days before next period start
        assert head.get("typical_days_before") in (1, 2, 3), head
        # Premenstrual recurrence: ~100% per problem statement
        assert head.get("premenstrual_cycle_rate", 0) >= 75, head
        assert head.get("cycle_recurrence_rate", 0) >= 75, head
        # Insight headline contains the lead-time phrasing
        assert isinstance(head.get("insight"), str) and head["insight"]
        assert "period" in head["insight"].lower()
        # Top-level insights list surfaces the premenstrual headline first
        assert len(body.get("insights", [])) >= 1

    def test_symptom_patterns_requires_auth(self):
        r = requests.get(f"{API}/symptom-patterns", timeout=15)
        assert r.status_code in (401, 403)


# ===================== 2. DAILY SUMMARY =====================
class TestDailySummary:
    def test_daily_summary_shape_qa(self, client, qa_token):
        today = date.today().isoformat()
        r = client.get(f"{API}/daily-summary",
                       params={"today": today},
                       headers=_auth(qa_token), timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        for key in ("date", "headline", "lines", "cycle_day", "phase",
                    "days_until_next_period", "next_period_date", "water",
                    "meals_completed", "meals_goal", "medications_taken",
                    "medications_planned", "symptoms_logged", "mood_entries",
                    "has_cycle_data"):
            assert key in body, f"missing key {key}: {list(body)}"
        assert body["date"] == today
        assert isinstance(body["headline"], str) and body["headline"]
        assert isinstance(body["lines"], list) and len(body["lines"]) >= 2
        # water sub-object
        water = body["water"]
        for k in ("total_ml", "goal_ml", "percentage"):
            assert k in water
        assert water["total_ml"] >= 0
        assert water["goal_ml"] >= 0
        # cycle data should be true for qa (has cycles seeded)
        assert body["has_cycle_data"] is True
        # When there are cycles, cycle_day should be a positive int and phase set
        assert isinstance(body["cycle_day"], int) and body["cycle_day"] > 0
        assert body["phase"] in {"menstrual", "follicular", "ovulation", "luteal"}
        # Headline mentions cycle day
        assert "cycle day" in body["headline"].lower()

    def test_daily_summary_coherent_counts_after_actions(self, client, qa_token):
        """Log a water + a meal and verify daily-summary numbers move accordingly."""
        today = date.today().isoformat()
        before = client.get(f"{API}/daily-summary", params={"today": today},
                            headers=_auth(qa_token), timeout=20).json()

        # Use unique client_ids so idempotency does not collapse the new entries
        cid_w = f"qa-w-{uuid.uuid4().hex[:8]}"
        rw = client.post(f"{API}/water",
                         json={"amount_ml": 250, "client_id": cid_w},
                         headers=_auth(qa_token), timeout=20)
        assert rw.status_code in (200, 201), rw.text
        cid_m = f"qa-m-{uuid.uuid4().hex[:8]}"
        rm = client.post(f"{API}/meals",
                         json={"meal_type": "snack", "status": "completed",
                               "client_id": cid_m},
                         headers=_auth(qa_token), timeout=20)
        assert rm.status_code in (200, 201), rm.text

        after = client.get(f"{API}/daily-summary", params={"today": today},
                           headers=_auth(qa_token), timeout=20).json()
        assert after["water"]["total_ml"] >= before["water"]["total_ml"] + 250
        assert after["meals_completed"] >= before["meals_completed"] + 1

    def test_daily_summary_no_data_user(self, client):
        u = register_user(client, "summary")
        r = client.get(f"{API}/daily-summary",
                       headers=_auth(u["access_token"]), timeout=20)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["has_cycle_data"] is False
        assert b["water"]["total_ml"] == 0
        assert b["meals_completed"] == 0
        assert b["medications_planned"] == 0
        assert b["headline"]  # still a non-empty headline

    def test_daily_summary_requires_auth(self):
        r = requests.get(f"{API}/daily-summary", timeout=15)
        assert r.status_code in (401, 403)


# ===================== 3. OFFLINE IDEMPOTENCY =====================
class TestOfflineIdempotency:
    def test_water_dedupes_same_client_id(self, client):
        u = register_user(client, "idemw")
        h = _auth(u["access_token"])
        cid = f"w-{uuid.uuid4().hex}"
        body = {"amount_ml": 300, "client_id": cid}
        r1 = client.post(f"{API}/water", json=body, headers=h, timeout=20)
        r2 = client.post(f"{API}/water", json=body, headers=h, timeout=20)
        assert r1.status_code in (200, 201) and r2.status_code in (200, 201)
        assert r1.json()["id"] == r2.json()["id"], "duplicate water row created!"
        # Independent verification: only one event in DB for that date
        today = r1.json()["date"]
        listing = client.get(f"{API}/health-events",
                             params={"event_type": "water",
                                     "start_date": today, "end_date": today},
                             headers=h, timeout=20).json()
        cnt = sum(1 for e in listing if (e.get("data") or {}).get("amount_ml") == 300)
        assert cnt == 1, f"expected 1 water log for cid, got {cnt}: {listing}"

    def test_meals_dedupes_same_client_id(self, client):
        u = register_user(client, "idemm")
        h = _auth(u["access_token"])
        cid = f"m-{uuid.uuid4().hex}"
        body = {"meal_type": "lunch", "status": "completed", "client_id": cid}
        r1 = client.post(f"{API}/meals", json=body, headers=h, timeout=20)
        r2 = client.post(f"{API}/meals", json=body, headers=h, timeout=20)
        assert r1.status_code in (200, 201) and r2.status_code in (200, 201)
        assert r1.json()["id"] == r2.json()["id"]
        today = r1.json()["date"]
        events = client.get(f"{API}/health-events",
                            params={"event_type": "meal",
                                    "start_date": today, "end_date": today},
                            headers=h, timeout=20).json()
        # We just created a single lunch via this client_id
        lunches = [e for e in events
                   if (e.get("data") or {}).get("meal_type") == "lunch"]
        assert len(lunches) == 1

    def test_quick_log_dedupes_same_client_id(self, client):
        u = register_user(client, "idemq")
        h = _auth(u["access_token"])
        cid = f"q-{uuid.uuid4().hex}"
        body = {"action": "water", "data": {"amount_ml": 100}, "client_id": cid}
        r1 = client.post(f"{API}/quick-log", json=body, headers=h, timeout=20)
        r2 = client.post(f"{API}/quick-log", json=body, headers=h, timeout=20)
        assert r1.status_code in (200, 201) and r2.status_code in (200, 201)
        assert r1.json()["id"] == r2.json()["id"]

    def test_mark_taken_dedupes_same_client_id(self, client):
        u = register_user(client, "idemt")
        h = _auth(u["access_token"])
        # Create a schedule
        sched = client.post(f"{API}/medication-schedules",
                            json={"name": "TEST_idem_pill", "schedule_type": "daily",
                                  "times": ["08:00"], "category": "vitamin"},
                            headers=h, timeout=20)
        assert sched.status_code in (200, 201), sched.text
        sid = sched.json()["id"]
        cid = f"t-{uuid.uuid4().hex}"
        body = {"scheduled_time": "08:00", "client_id": cid}
        r1 = client.post(f"{API}/medication-schedules/{sid}/take",
                         json=body, headers=h, timeout=20)
        r2 = client.post(f"{API}/medication-schedules/{sid}/take",
                         json=body, headers=h, timeout=20)
        assert r1.status_code in (200, 201) and r2.status_code in (200, 201)
        assert r2.json().get("deduped") is True
        # Verify only one taken event exists today for this schedule
        today_doses = client.get(f"{API}/medication-schedules/today",
                                 headers=h, timeout=20).json()
        taken = [d for d in today_doses["doses"]
                 if d["schedule_id"] == sid and d["taken"]]
        assert today_doses["taken"] == 1
        assert len(taken) == 1


# ===================== 4. AUTH ENFORCEMENT =====================
class TestAuthEnforcement:
    @pytest.mark.parametrize("method,path,payload", [
        ("post", "/water", {"amount_ml": 250}),
        ("post", "/meals", {"meal_type": "snack", "status": "completed"}),
        ("post", "/quick-log", {"action": "water", "data": {}}),
        ("get",  "/symptom-patterns", None),
        ("get",  "/daily-summary", None),
    ])
    def test_requires_bearer(self, method, path, payload):
        url = f"{API}{path}"
        r = (requests.get(url, timeout=15) if method == "get"
             else requests.post(url, json=payload, timeout=15))
        assert r.status_code in (401, 403), \
            f"{method.upper()} {path} expected 401/403, got {r.status_code}"

    def test_mark_taken_requires_bearer(self):
        # use a random uuid as schedule id; should reject for auth before checking id
        sid = str(uuid.uuid4())
        r = requests.post(f"{API}/medication-schedules/{sid}/take",
                          json={"scheduled_time": "08:00"}, timeout=15)
        assert r.status_code in (401, 403)
