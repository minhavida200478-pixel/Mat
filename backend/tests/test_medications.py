"""Tests for Smart Medication Reminders + Adherence (medications_v2.py)."""
import os
from datetime import date, timedelta

import pytest
import requests

from tests.conftest import API, register_user


# ----------------------------- Helpers -----------------------------
def _auth(headers_token: str) -> dict:
    return {"Authorization": f"Bearer {headers_token}", "Content-Type": "application/json"}


def _create_schedule(client, headers, body):
    return client.post(f"{API}/medication-schedules", json=body, headers=headers, timeout=20)


# ----------------------------- Auth enforcement -----------------------------
class TestMedicationsAuth:
    def test_list_requires_auth(self, client):
        r = client.get(f"{API}/medication-schedules", timeout=20)
        assert r.status_code in (401, 403), r.text

    def test_today_requires_auth(self, client):
        r = client.get(f"{API}/medication-schedules/today", timeout=20)
        assert r.status_code in (401, 403)

    def test_adherence_requires_auth(self, client):
        r = client.get(f"{API}/medication-schedules/adherence?days=30", timeout=20)
        assert r.status_code in (401, 403)

    def test_create_requires_auth(self, client):
        r = client.post(f"{API}/medication-schedules",
                        json={"name": "X", "times": ["08:00"]}, timeout=20)
        assert r.status_code in (401, 403)


# ----------------------------- CRUD + validation -----------------------------
class TestMedicationCRUD:
    @pytest.fixture(scope="class")
    def user(self, client_class):
        return register_user(client_class, "med")

    @pytest.fixture(scope="class")
    def client_class(self):
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        return s

    @pytest.fixture
    def headers(self, user):
        return _auth(user["access_token"])

    def test_create_daily_with_times(self, client_class, headers):
        body = {"name": "TEST_Vitamin C", "dosage": "500mg",
                "category": "vitamin", "schedule_type": "daily",
                "times": ["08:00", "20:00"], "enabled": True}
        r = _create_schedule(client_class, headers, body)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["name"] == "TEST_Vitamin C"
        assert d["schedule_type"] == "daily"
        assert d["times"] == ["08:00", "20:00"]
        assert d["enabled"] is True
        assert "id" in d
        # GET to verify persistence
        gl = client_class.get(f"{API}/medication-schedules", headers=headers, timeout=20)
        assert gl.status_code == 200
        names = [s["name"] for s in gl.json()]
        assert "TEST_Vitamin C" in names

    def test_create_daily_without_times_400(self, client_class, headers):
        body = {"name": "TEST_NoTimes", "schedule_type": "daily", "times": []}
        r = _create_schedule(client_class, headers, body)
        assert r.status_code == 400, r.text

    def test_create_cycle_based_without_times_400(self, client_class, headers):
        body = {"name": "TEST_CBNoTimes", "schedule_type": "cycle_based",
                "times": [], "cycle_days": [1, 2]}
        r = _create_schedule(client_class, headers, body)
        assert r.status_code == 400

    def test_create_cycle_based_without_cycle_days_400(self, client_class, headers):
        body = {"name": "TEST_CBNoDays", "schedule_type": "cycle_based",
                "times": ["10:00"], "cycle_days": []}
        r = _create_schedule(client_class, headers, body)
        assert r.status_code == 400

    def test_create_interval_zero_400(self, client_class, headers):
        body = {"name": "TEST_BadInt", "schedule_type": "interval",
                "interval_hours": 0, "interval_start": "08:00"}
        r = _create_schedule(client_class, headers, body)
        assert r.status_code == 400

    def test_create_interval_expands_times(self, client_class, headers):
        body = {"name": "TEST_Ibu", "dosage": "400mg",
                "category": "painkiller", "schedule_type": "interval",
                "interval_hours": 8, "interval_start": "08:00"}
        r = _create_schedule(client_class, headers, body)
        assert r.status_code == 200, r.text
        d = r.json()
        # 08:00, 16:00 (24:00 excluded since < 24*60)
        assert "08:00" in d["times"]
        assert "16:00" in d["times"]
        assert len(d["times"]) >= 2
        assert d["interval_hours"] == 8

    def test_update_and_delete(self, client_class, headers):
        body = {"name": "TEST_ToUpdate", "schedule_type": "daily",
                "times": ["09:00"]}
        r = _create_schedule(client_class, headers, body)
        assert r.status_code == 200
        sid = r.json()["id"]

        upd = {"name": "TEST_Updated", "schedule_type": "daily",
               "times": ["10:00", "22:00"], "category": "supplement",
               "enabled": False}
        ru = client_class.put(f"{API}/medication-schedules/{sid}",
                              json=upd, headers=headers, timeout=20)
        assert ru.status_code == 200, ru.text
        u = ru.json()
        assert u["name"] == "TEST_Updated"
        assert u["times"] == ["10:00", "22:00"]
        assert u["enabled"] is False

        # GET-verify
        gl = client_class.get(f"{API}/medication-schedules", headers=headers, timeout=20).json()
        match = next((s for s in gl if s["id"] == sid), None)
        assert match is not None and match["name"] == "TEST_Updated"

        # Delete
        rd = client_class.delete(f"{API}/medication-schedules/{sid}", headers=headers, timeout=20)
        assert rd.status_code == 200

        gl2 = client_class.get(f"{API}/medication-schedules", headers=headers, timeout=20).json()
        assert all(s["id"] != sid for s in gl2)


# ----------------------------- Today + Mark taken -----------------------------
class TestTodayAndMarkTaken:
    @pytest.fixture(scope="class")
    def client_class(self):
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        return s

    @pytest.fixture(scope="class")
    def user(self, client_class):
        return register_user(client_class, "today")

    @pytest.fixture(scope="class")
    def headers(self, user):
        return _auth(user["access_token"])

    @pytest.fixture(scope="class")
    def daily_id(self, client_class, headers):
        body = {"name": "TEST_DailyToday", "schedule_type": "daily",
                "times": ["08:00", "20:00"]}
        r = _create_schedule(client_class, headers, body)
        assert r.status_code == 200
        return r.json()["id"]

    def test_today_lists_planned(self, client_class, headers, daily_id):
        today = date.today().isoformat()
        r = client_class.get(f"{API}/medication-schedules/today?today={today}",
                             headers=headers, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d["date"] == today
        assert d["total"] >= 2
        assert d["taken"] == 0
        assert d["pending"] == d["total"]
        # The two planned slots should be present and not yet taken
        slots = [(x["schedule_id"], x["time"], x["taken"]) for x in d["doses"]]
        assert (daily_id, "08:00", False) in slots
        assert (daily_id, "20:00", False) in slots

    def test_mark_taken_reflects_in_today(self, client_class, headers, daily_id):
        today = date.today().isoformat()
        r = client_class.post(
            f"{API}/medication-schedules/{daily_id}/take",
            json={"scheduled_time": "08:00"}, headers=headers, timeout=20)
        assert r.status_code == 200, r.text

        td = client_class.get(f"{API}/medication-schedules/today?today={today}",
                              headers=headers, timeout=20).json()
        match = next((x for x in td["doses"]
                      if x["schedule_id"] == daily_id and x["time"] == "08:00"), None)
        assert match is not None and match["taken"] is True
        assert td["taken"] >= 1

    def test_mark_taken_404_for_unknown(self, client_class, headers):
        r = client_class.post(f"{API}/medication-schedules/does-not-exist/take",
                              json={}, headers=headers, timeout=20)
        assert r.status_code == 404


# ----------------------------- Cycle-based gating -----------------------------
class TestCycleBasedSchedule:
    @pytest.fixture(scope="class")
    def client_class(self):
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        return s

    @pytest.fixture(scope="class")
    def user(self, client_class):
        return register_user(client_class, "cyc")

    @pytest.fixture(scope="class")
    def headers(self, user):
        return _auth(user["access_token"])

    def test_cycle_based_returns_dose_on_active_day(self, client_class, headers):
        # Start cycle 2 days ago -> today is cycle day 3
        start = (date.today() - timedelta(days=2)).isoformat()
        rc = client_class.post(f"{API}/cycles", json={"start_date": start},
                               headers=headers, timeout=20)
        assert rc.status_code == 200, rc.text

        body = {"name": "TEST_Iron", "dosage": "65mg", "category": "supplement",
                "schedule_type": "cycle_based", "times": ["10:00"],
                "cycle_days": [1, 2, 3, 4, 5]}
        r = _create_schedule(client_class, headers, body)
        assert r.status_code == 200, r.text
        sid = r.json()["id"]

        today = date.today().isoformat()
        td = client_class.get(f"{API}/medication-schedules/today?today={today}",
                              headers=headers, timeout=20).json()
        # Iron should appear today (cycle day 3)
        assert any(x["schedule_id"] == sid and x["time"] == "10:00" for x in td["doses"])

    def test_cycle_based_excluded_outside_window(self, client_class, headers):
        body = {"name": "TEST_IronOff", "schedule_type": "cycle_based",
                "times": ["09:00"], "cycle_days": [25, 26, 27]}
        r = _create_schedule(client_class, headers, body)
        assert r.status_code == 200
        sid = r.json()["id"]
        today = date.today().isoformat()
        td = client_class.get(f"{API}/medication-schedules/today?today={today}",
                              headers=headers, timeout=20).json()
        assert all(x["schedule_id"] != sid for x in td["doses"])


# ----------------------------- Adherence -----------------------------
class TestAdherence:
    @pytest.fixture(scope="class")
    def client_class(self):
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        return s

    @pytest.fixture(scope="class")
    def user(self, client_class):
        return register_user(client_class, "adh")

    @pytest.fixture(scope="class")
    def headers(self, user):
        return _auth(user["access_token"])

    def test_adherence_structure_and_creation_floor(self, client_class, headers):
        body = {"name": "TEST_AdhDaily", "schedule_type": "daily",
                "times": ["08:00", "20:00"]}
        r = _create_schedule(client_class, headers, body)
        assert r.status_code == 200
        sid = r.json()["id"]

        today = date.today().isoformat()
        adh = client_class.get(
            f"{API}/medication-schedules/adherence?days=30&today={today}",
            headers=headers, timeout=20)
        assert adh.status_code == 200, adh.text
        a = adh.json()
        for k in ("days", "has_data", "overall_percentage", "expected_total",
                  "taken_total", "streak_days", "active_medications",
                  "medications", "recent"):
            assert k in a, f"missing key: {k}"
        assert a["days"] == 30
        # Only today's doses count (schedule created today); not 30*2=60
        assert a["expected_total"] == 2
        assert a["taken_total"] == 0
        assert a["streak_days"] == 0
        assert len(a["recent"]) == 7
        # 7-day recent array dates land in the last 7 days
        rec_dates = [r["date"] for r in a["recent"]]
        assert rec_dates[-1] == today
        # Per-medication breakdown contains our schedule with percentage
        sched_row = next((m for m in a["medications"] if m["schedule_id"] == sid), None)
        assert sched_row is not None
        assert sched_row["expected"] == 2
        assert sched_row["taken"] == 0
        assert sched_row["percentage"] == 0

    def test_adherence_updates_after_taking_dose(self, client_class, headers):
        # Mark one dose taken today -> overall + per-med taken should bump
        sched = client_class.get(f"{API}/medication-schedules",
                                 headers=headers, timeout=20).json()
        sid = next(s["id"] for s in sched if s["name"] == "TEST_AdhDaily")
        rt = client_class.post(f"{API}/medication-schedules/{sid}/take",
                               json={"scheduled_time": "08:00"},
                               headers=headers, timeout=20)
        assert rt.status_code == 200

        today = date.today().isoformat()
        a = client_class.get(
            f"{API}/medication-schedules/adherence?days=30&today={today}",
            headers=headers, timeout=20).json()
        assert a["taken_total"] >= 1
        # 1 of 2 = 50%
        assert a["overall_percentage"] == 50

    def test_adherence_invalid_days_param(self, client, fresh_user):
        h = _auth(fresh_user["access_token"])
        r = client.get(f"{API}/medication-schedules/adherence?days=1",
                       headers=h, timeout=20)
        # ge=7, so 1 -> 422
        assert r.status_code == 422


# ----------------------------- Seeded qa@cycle.app user -----------------------------
class TestSeededQAUser:
    """Validates the seeded qa@cycle.app account works as the review_request claims."""

    @pytest.fixture(scope="class")
    def client_class(self):
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        return s

    @pytest.fixture(scope="class")
    def qa_headers(self, client_class):
        r = client_class.post(f"{API}/auth/login",
                              json={"email": "qa@cycle.app", "password": "Test1234!"},
                              timeout=20)
        if r.status_code != 200:
            pytest.skip(f"qa@cycle.app not seeded: {r.status_code}")
        tok = r.json()["access_token"]
        return _auth(tok)

    def test_qa_has_three_schedules(self, client_class, qa_headers):
        r = client_class.get(f"{API}/medication-schedules",
                             headers=qa_headers, timeout=20)
        assert r.status_code == 200
        names = [s["name"] for s in r.json()]
        # The note says: Vitamin D, Ibuprofen, Iron
        assert len(r.json()) >= 3, names

    def test_qa_today_includes_iron(self, client_class, qa_headers):
        today = date.today().isoformat()
        r = client_class.get(f"{API}/medication-schedules/today?today={today}",
                             headers=qa_headers, timeout=20)
        assert r.status_code == 200
        d = r.json()
        # Iron is days 1-5 @10:00, cycle ~4 days ago => cycle day ~5 -> should appear
        names = [x["name"] for x in d["doses"]]
        assert any("Iron" in n for n in names), names

    def test_qa_adherence_basic_shape(self, client_class, qa_headers):
        today = date.today().isoformat()
        r = client_class.get(
            f"{API}/medication-schedules/adherence?days=30&today={today}",
            headers=qa_headers, timeout=20)
        assert r.status_code == 200
        a = r.json()
        assert a["active_medications"] >= 3
        assert len(a["recent"]) == 7
        assert isinstance(a["streak_days"], int)
