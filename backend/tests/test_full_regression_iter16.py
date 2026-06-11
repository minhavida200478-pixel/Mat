"""Iter-16 full-app regression — exercises EVERY non-partner endpoint end-to-end on
ONE rich seeded user (so analytics/predictions are populated) plus auth-gating and
isolation checks on a second user. Partner endpoints are covered by the existing
partner_* suites and only smoke-checked here (list).

Designed to be deterministic with the production 10/min register rate-limit:
total fresh registrations = 2 (rich + isolation) + 1 forgot-password user (3).
"""
import time
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from tests.conftest import API, register_user

TODAY = date.today()
ISO = lambda d: d.isoformat()  # noqa


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ----------------------------- Rich seeded user fixture -----------------------------
@pytest.fixture(scope="module")
def rich_user(): ...


@pytest.fixture(scope="module")
def session_client():
    import requests
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def rich(session_client):
    """Register a fresh user and seed:
       - 6 regular 28-day cycles (so prediction has high confidence)
       - 5 daily logs with recurring symptoms/moods
       - water/meal/medication events for the last 7 days
       - 1 medication schedule (daily 08:00)
    """
    user = register_user(session_client, "rich")
    h = _auth(user["access_token"])

    # ---- Cycles: 6 prior 28-day cycles + most recent ~14 days ago
    today = TODAY
    # last period start = today - 14d, previous = -42, ..., totaling 6 cycles.
    starts = [today - timedelta(days=14 + 28 * i) for i in range(6)]
    for s in starts:
        r = session_client.post(f"{API}/cycles", json={
            "start_date": ISO(s), "end_date": ISO(s + timedelta(days=4))}, headers=h)
        assert r.status_code in (200, 201, 409), r.text

    # ---- Daily logs: last 5 days with recurring "Headache" + moods
    moods_rot = [["Tired"], ["Happy"], ["Anxious"], ["Tired"], ["Calm"]]
    for i in range(5):
        d = ISO(today - timedelta(days=i))
        r = session_client.post(f"{API}/logs", json={
            "date": d,
            "symptoms": [{"name": "Headache", "severity": "moderate"},
                         {"name": "Cramps", "severity": "mild"}],
            "moods": moods_rot[i],
            "note": f"day {i}", "tags": ["test"], "visibility": "private",
        }, headers=h)
        assert r.status_code == 200, r.text

    # ---- Water events: last 7 days, 4x250ml = 1000ml/day (vs default 2000 goal)
    for i in range(7):
        ts = (datetime.now(timezone.utc) - timedelta(days=i)).isoformat()
        for _ in range(4):
            r = session_client.post(f"{API}/water",
                                    json={"amount_ml": 250, "timestamp": ts},
                                    headers=h)
            assert r.status_code == 200, r.text

    # ---- Meal events: today breakfast + lunch
    for mt in ("breakfast", "lunch"):
        r = session_client.post(f"{API}/meals",
                                json={"meal_type": mt, "status": "completed"},
                                headers=h)
        assert r.status_code == 200, r.text

    # ---- Medication schedule (daily 08:00) + one taken today
    rsched = session_client.post(f"{API}/medication-schedules", json={
        "name": "TEST_Vitamin", "dosage": "1 tab", "category": "vitamin",
        "schedule_type": "daily", "times": ["08:00"], "enabled": True,
    }, headers=h)
    assert rsched.status_code == 200, rsched.text
    sched_id = rsched.json()["id"]
    r = session_client.post(f"{API}/medication-schedules/{sched_id}/take",
                            json={"scheduled_time": "08:00"}, headers=h)
    assert r.status_code == 200

    return {"user": user, "headers": h, "schedule_id": sched_id,
            "client": session_client}


# =================================================================
# AUTH
# =================================================================
class TestAuth:
    def test_me_returns_user(self, rich):
        r = rich["client"].get(f"{API}/auth/me", headers=rich["headers"])
        assert r.status_code == 200
        body = r.json()
        assert body["email"].lower() == rich["user"]["email"].lower()
        assert "id" in body

    def test_protected_without_token_is_401(self, rich):
        r = rich["client"].get(f"{API}/dashboard")
        assert r.status_code in (401, 403)

    def test_protected_with_bad_token_is_401(self, rich):
        r = rich["client"].get(f"{API}/dashboard",
                               headers={"Authorization": "Bearer not.a.jwt"})
        assert r.status_code == 401

    def test_login_wrong_password_401(self, rich):
        r = rich["client"].post(f"{API}/auth/login", json={
            "email": rich["user"]["email"], "password": "WRONG_pw_x9"})
        assert r.status_code == 401

    def test_refresh_rotates_tokens(self, rich):
        r = rich["client"].post(f"{API}/auth/refresh",
                                json={"refresh_token": rich["user"]["refresh_token"]})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["access_token"] and body["refresh_token"]
        # refresh token must differ from the one we sent (single-use rotation)
        assert body["refresh_token"] != rich["user"]["refresh_token"]
        # update fixture so subsequent tests stay valid (refresh consumed old one)
        rich["user"]["access_token"] = body["access_token"]
        rich["user"]["refresh_token"] = body["refresh_token"]
        rich["headers"].update({"Authorization": f"Bearer {body['access_token']}"})

    def test_forgot_password_is_generic_200(self, session_client):
        # Always 200 regardless of whether email exists (anti-enumeration).
        r = session_client.post(f"{API}/auth/forgot-password",
                                json={"email": f"nobody_{uuid.uuid4().hex[:6]}@cycle.app"})
        assert r.status_code == 200
        assert "reset code" in r.json()["detail"].lower()

    def test_reset_password_invalid_code_400(self, session_client):
        r = session_client.post(f"{API}/auth/reset-password", json={
            "email": "demo@cycle.app", "code": "000000",
            "new_password": "NewPass123!"})
        assert r.status_code == 400


# =================================================================
# CYCLES
# =================================================================
class TestCycles:
    def test_list_cycles_returns_seeded(self, rich):
        r = rich["client"].get(f"{API}/cycles", headers=rich["headers"])
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        assert len(rows) >= 6, f"expected 6+ seeded cycles, got {len(rows)}"
        assert all("id" in c and "start_date" in c for c in rows)

    def test_create_duplicate_cycle_409(self, rich):
        existing_start = ISO(TODAY - timedelta(days=14))
        r = rich["client"].post(f"{API}/cycles",
                                json={"start_date": existing_start},
                                headers=rich["headers"])
        assert r.status_code == 409

    def test_update_and_delete_cycle(self, rich):
        # create a temp cycle that doesn't overlap a seeded start_date
        tmp_start = ISO(TODAY - timedelta(days=400))
        c = rich["client"].post(f"{API}/cycles",
                                json={"start_date": tmp_start},
                                headers=rich["headers"]).json()
        cid = c["id"]
        # update
        r = rich["client"].put(f"{API}/cycles/{cid}", json={
            "end_date": ISO(TODAY - timedelta(days=396))}, headers=rich["headers"])
        assert r.status_code == 200
        # verify via GET
        rows = rich["client"].get(f"{API}/cycles", headers=rich["headers"]).json()
        match = next((x for x in rows if x["id"] == cid), None)
        assert match and match["end_date"] == ISO(TODAY - timedelta(days=396))
        # delete (soft) — idempotent: second delete still returns 200 (matches by _id)
        r = rich["client"].delete(f"{API}/cycles/{cid}", headers=rich["headers"])
        assert r.status_code == 200
        # absent from list
        rows = rich["client"].get(f"{API}/cycles", headers=rich["headers"]).json()
        assert not any(x["id"] == cid for x in rows)
        # nonexistent id -> 404
        r = rich["client"].delete(f"{API}/cycles/does-not-exist", headers=rich["headers"])
        assert r.status_code == 404


# =================================================================
# DAILY LOGS + QUICK-LOG
# =================================================================
class TestLogs:
    def test_list_logs(self, rich):
        r = rich["client"].get(f"{API}/logs", headers=rich["headers"])
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) >= 5
        # The seeded log for "today" must contain Headache symptom
        today_row = next((x for x in rows if x["date"] == ISO(TODAY)), None)
        assert today_row
        names = [s["name"] for s in today_row["symptoms"]]
        assert "Headache" in names

    def test_get_log_by_date(self, rich):
        r = rich["client"].get(f"{API}/logs/{ISO(TODAY)}", headers=rich["headers"])
        assert r.status_code == 200
        assert r.json()["date"] == ISO(TODAY)

    def test_get_log_missing_date_returns_empty(self, rich):
        r = rich["client"].get(f"{API}/logs/1990-01-01", headers=rich["headers"])
        assert r.status_code == 200
        assert r.json()["symptoms"] == []

    def test_quick_log_water_creates_event(self, rich):
        r = rich["client"].post(f"{API}/quick-log",
                                json={"action": "water", "data": {"amount_ml": 500}},
                                headers=rich["headers"])
        assert r.status_code == 200
        body = r.json()
        assert body["event_type"] == "water"
        assert body["data"]["amount_ml"] == 500


# =================================================================
# DASHBOARD / PREDICTIONS / SUMMARIES
# =================================================================
class TestDashboard:
    def test_dashboard_has_prediction(self, rich):
        r = rich["client"].get(f"{API}/dashboard", headers=rich["headers"])
        assert r.status_code == 200
        body = r.json()
        assert "prediction" in body
        pred = body["prediction"]
        assert pred.get("has_data") is True
        assert pred.get("cycle_day") is not None
        assert pred.get("next_period_date")
        assert pred.get("avg_cycle_length")
        assert isinstance(pred.get("days_until_next_period"), int)

    def test_daily_summary(self, rich):
        r = rich["client"].get(f"{API}/daily-summary", headers=rich["headers"])
        assert r.status_code == 200
        body = r.json()
        # Field names depend on impl — check a few stable ones
        assert "next_period_date" in body or "period_line" in body or "cycle_day" in body

    def test_widget_summary(self, rich):
        r = rich["client"].get(f"{API}/widget-summary", headers=rich["headers"])
        assert r.status_code == 200
        body = r.json()
        # widget exposes hydration progress; meals_logged
        assert "meals_logged" in body or "water_percentage" in body or "cycle_day" in body


# =================================================================
# ANALYTICS / GRAPHS
# =================================================================
class TestAnalytics:
    def test_analytics_has_cycle_history(self, rich):
        r = rich["client"].get(f"{API}/analytics", headers=rich["headers"])
        assert r.status_code == 200
        body = r.json()
        # Must have enough data for graph rendering
        assert isinstance(body, dict)
        # Common keys: cycle_length_history, mood_freq, symptom_freq, avg_cycle_length
        # At minimum verify the response has *some* cycle data (frontend chart fuel)
        text = str(body).lower()
        assert any(k in text for k in ("cycle_length", "history", "avg"))

    def test_water_analytics_returns_days(self, rich):
        r = rich["client"].get(f"{API}/water/analytics?days=7", headers=rich["headers"])
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, dict)
        # response should contain per-day points for the chart
        days_payload = body.get("days") or body.get("daily") or body.get("data") or body
        # Check non-empty
        assert days_payload, f"water analytics empty: {body}"

    def test_symptom_patterns(self, rich):
        r = rich["client"].get(f"{API}/symptom-patterns", headers=rich["headers"])
        assert r.status_code == 200
        body = r.json()
        # has_enough_data + symptoms list expected; even if False the endpoint must return 200
        assert isinstance(body, dict)
        assert "symptoms" in body or "has_enough_data" in body

    def test_symptom_intelligence(self, rich):
        r = rich["client"].get(f"{API}/symptom-intelligence", headers=rich["headers"])
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_medication_adherence(self, rich):
        r = rich["client"].get(f"{API}/medication-schedules/adherence?days=7",
                               headers=rich["headers"])
        assert r.status_code == 200
        body = r.json()
        # daily series for chart
        assert any(k in body for k in (
            "daily", "overall", "adherence", "expected_total", "taken_total", "has_data"))


# =================================================================
# HYDRATION
# =================================================================
class TestHydration:
    def test_water_today_has_logs(self, rich):
        r = rich["client"].get(f"{API}/water/today", headers=rich["headers"])
        assert r.status_code == 200
        body = r.json()
        assert body["date"] == ISO(TODAY)
        assert body["total_ml"] >= 1000  # 4x250 seeded
        assert body["goal_ml"] >= 1
        assert isinstance(body["logs"], list)

    def test_water_by_date(self, rich):
        r = rich["client"].get(f"{API}/water/{ISO(TODAY)}", headers=rich["headers"])
        assert r.status_code == 200
        assert r.json()["date"] == ISO(TODAY)

    def test_water_goal_update_persists(self, rich):
        r = rich["client"].put(f"{API}/water/goal", json={"goal_ml": 2500},
                               headers=rich["headers"])
        assert r.status_code == 200
        r2 = rich["client"].get(f"{API}/water/today", headers=rich["headers"])
        assert r2.json()["goal_ml"] == 2500


# =================================================================
# MEALS
# =================================================================
class TestMeals:
    def test_meals_today_counts(self, rich):
        r = rich["client"].get(f"{API}/meals/today", headers=rich["headers"])
        assert r.status_code == 200
        body = r.json()
        # we seeded breakfast + lunch
        assert body.get("completed_count", 0) >= 2

    def test_meals_by_date(self, rich):
        r = rich["client"].get(f"{API}/meals/{ISO(TODAY)}", headers=rich["headers"])
        assert r.status_code == 200
        assert r.json()["date"] == ISO(TODAY)


# =================================================================
# MEDICATIONS (legacy log) + SCHEDULES
# =================================================================
class TestMedications:
    def test_log_medication_creates_event(self, rich):
        r = rich["client"].post(f"{API}/medications", json={
            "name": "TEST_Ibuprofen", "dosage": "200mg",
            "category": "painkiller"}, headers=rich["headers"])
        assert r.status_code == 200
        body = r.json()
        assert body["event_type"] == "medication"

    def test_medications_today_and_history(self, rich):
        r = rich["client"].get(f"{API}/medications/today", headers=rich["headers"])
        assert r.status_code == 200
        assert isinstance(r.json(), (list, dict))
        r = rich["client"].get(f"{API}/medications/history", headers=rich["headers"])
        assert r.status_code == 200
        assert isinstance(r.json(), (list, dict))

    def test_schedules_list_and_today(self, rich):
        r = rich["client"].get(f"{API}/medication-schedules", headers=rich["headers"])
        assert r.status_code == 200
        rows = r.json()
        assert any(s["id"] == rich["schedule_id"] for s in rows)
        r = rich["client"].get(f"{API}/medication-schedules/today",
                               headers=rich["headers"])
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 1
        assert body["taken"] >= 1  # we marked one taken in the fixture

    def test_schedule_update_and_delete(self, rich):
        # create temp schedule
        r = rich["client"].post(f"{API}/medication-schedules", json={
            "name": "TEST_TempMed", "schedule_type": "daily",
            "times": ["09:00"]}, headers=rich["headers"])
        assert r.status_code == 200
        sid = r.json()["id"]
        # update
        r = rich["client"].put(f"{API}/medication-schedules/{sid}", json={
            "name": "TEST_TempMed_v2", "schedule_type": "daily",
            "times": ["10:00"]}, headers=rich["headers"])
        assert r.status_code == 200
        assert r.json()["name"] == "TEST_TempMed_v2"
        # delete
        r = rich["client"].delete(f"{API}/medication-schedules/{sid}",
                                  headers=rich["headers"])
        assert r.status_code == 200
        # nonexistent id -> 404
        r = rich["client"].delete(f"{API}/medication-schedules/does-not-exist",
                                  headers=rich["headers"])
        assert r.status_code == 404


# =================================================================
# SEXUAL ACTIVITY
# =================================================================
class TestSexualActivity:
    def test_log_and_history(self, rich):
        r = rich["client"].post(f"{API}/sexual-activity", json={
            "protection_used": True, "partner_present": True,
            "share_with_partner": False}, headers=rich["headers"])
        assert r.status_code == 200
        body = r.json()
        assert body["event_type"] == "sexual_activity"
        r = rich["client"].get(f"{API}/sexual-activity/history",
                               headers=rich["headers"])
        assert r.status_code == 200
        items = r.json()
        if isinstance(items, dict):
            items = items.get("items", items.get("logs", []))
        assert isinstance(items, list)
        assert len(items) >= 1


# =================================================================
# HEALTH EVENTS unified CRUD
# =================================================================
class TestHealthEvents:
    def test_create_get_update_delete(self, rich):
        ts = datetime.now(timezone.utc).isoformat()
        r = rich["client"].post(f"{API}/health-events", json={
            "event_type": "note", "timestamp": ts, "date": ts[:10],
            "data": {"text": "TEST_he"}, "note": "TEST_he", "visibility": "private",
            "tags": ["test"]}, headers=rich["headers"])
        assert r.status_code == 200, r.text
        eid = r.json()["id"]

        r = rich["client"].get(f"{API}/health-events/{eid}", headers=rich["headers"])
        assert r.status_code == 200
        assert r.json()["note"] == "TEST_he"

        r = rich["client"].put(f"{API}/health-events/{eid}", json={
            "event_type": "note", "timestamp": ts, "date": ts[:10],
            "data": {"text": "TEST_he_v2"}, "note": "TEST_he_v2",
            "visibility": "private", "tags": ["test"]},
                               headers=rich["headers"])
        assert r.status_code == 200

        r = rich["client"].get(f"{API}/health-events/{eid}", headers=rich["headers"])
        assert r.json()["note"] == "TEST_he_v2"

        r = rich["client"].delete(f"{API}/health-events/{eid}", headers=rich["headers"])
        assert r.status_code == 200

        r = rich["client"].get(f"{API}/health-events/{eid}", headers=rich["headers"])
        assert r.status_code == 404

    def test_list_filters(self, rich):
        r = rich["client"].get(
            f"{API}/health-events?event_type=water&limit=5",
            headers=rich["headers"])
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        assert all(x["event_type"] == "water" for x in rows)


# =================================================================
# TIMELINE / SEARCH
# =================================================================
class TestTimelineSearch:
    def test_timeline_not_empty(self, rich):
        r = rich["client"].get(f"{API}/timeline", headers=rich["headers"])
        assert r.status_code == 200
        body = r.json()
        # accept either {items: [...]} or [...]
        items = body if isinstance(body, list) else (
            body.get("items") or body.get("events") or body.get("timeline") or [])
        assert items, f"timeline empty: {body}"

    def test_search_returns_dict(self, rich):
        r = rich["client"].get(f"{API}/search?q=TEST_he", headers=rich["headers"])
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, (list, dict))


# =================================================================
# BACKUP + AUDIT
# =================================================================
class TestBackupAndAudit:
    def test_backup_create_list_restore_delete(self, rich):
        # create
        r = rich["client"].post(f"{API}/backup", headers=rich["headers"])
        assert r.status_code == 200
        bid = r.json()["id"]
        total_before = r.json()["total"]
        assert total_before > 0
        # list
        r = rich["client"].get(f"{API}/backups", headers=rich["headers"])
        assert r.status_code == 200
        assert any(b["id"] == bid for b in r.json())
        # ensure-weekly is idempotent (no-op when recent auto exists OR creates one)
        r = rich["client"].post(f"{API}/backups/ensure-weekly",
                                headers=rich["headers"])
        assert r.status_code == 200
        # restore
        r = rich["client"].post(f"{API}/backups/{bid}/restore",
                                headers=rich["headers"])
        assert r.status_code == 200
        assert r.json()["total"] == total_before
        # delete
        r = rich["client"].delete(f"{API}/backups/{bid}", headers=rich["headers"])
        assert r.status_code == 200
        r = rich["client"].delete(f"{API}/backups/{bid}", headers=rich["headers"])
        assert r.status_code == 404

    def test_audit_logs(self, rich):
        r = rich["client"].get(f"{API}/audit-logs?limit=10", headers=rich["headers"])
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        assert isinstance(body["items"], list)
        assert len(body["items"]) >= 1


# =================================================================
# PARTNER smoke
# =================================================================
class TestPartnerSmoke:
    def test_partner_links_empty_for_fresh_user(self, rich):
        r = rich["client"].get(f"{API}/partner/links", headers=rich["headers"])
        assert r.status_code == 200
        body = r.json()
        # Two-list shape (as_owner / as_partner) per partner_router
        assert isinstance(body, dict)
        assert "sharing" in body or "viewing" in body or "as_owner" in body or "links" in body


# =================================================================
# ISOLATION (user B can't read user A's resources)
# =================================================================
@pytest.fixture(scope="module")
def isolation_user(session_client):
    return register_user(session_client, "iso")


class TestIsolation:
    def test_cycle_other_user_404(self, rich, isolation_user):
        # create a cycle on rich, then try to delete via iso user
        c = rich["client"].post(f"{API}/cycles", json={
            "start_date": ISO(TODAY - timedelta(days=500))},
                                headers=rich["headers"]).json()
        cid = c["id"]
        h_iso = _auth(isolation_user["access_token"])
        r = rich["client"].delete(f"{API}/cycles/{cid}", headers=h_iso)
        assert r.status_code == 404
        # cleanup
        rich["client"].delete(f"{API}/cycles/{cid}", headers=rich["headers"])

    def test_health_event_isolation(self, rich, isolation_user):
        ts = datetime.now(timezone.utc).isoformat()
        e = rich["client"].post(f"{API}/health-events", json={
            "event_type": "note", "timestamp": ts, "date": ts[:10],
            "data": {}, "note": "iso_test"}, headers=rich["headers"]).json()
        eid = e["id"]
        h_iso = _auth(isolation_user["access_token"])
        r = rich["client"].get(f"{API}/health-events/{eid}", headers=h_iso)
        assert r.status_code == 404
        rich["client"].delete(f"{API}/health-events/{eid}", headers=rich["headers"])
