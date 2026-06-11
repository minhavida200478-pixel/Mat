"""Part 2 production-readiness QA audit:
Prediction engine math, symptoms, moods, notes, hydration, meals, sexual activity,
medications, daily summary, widget summary, and partner privacy gating for activity.
"""
import os
import time
import uuid
from datetime import date, datetime, timedelta

import pytest
import requests

BASE = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
        or "https://mat-build.preview.emergentagent.com").rstrip("/") + "/api"


def _u():
    return f"TEST_qa2_{uuid.uuid4().hex[:10]}@cycle.app"


@pytest.fixture(scope="module")
def user():
    """Register a fresh user, return (token, email)."""
    email, pw = _u(), "Password123!"
    for _ in range(3):
        r = requests.post(f"{BASE}/auth/register",
                          json={"email": email, "password": pw, "full_name": "QA2"})
        if r.status_code == 201:
            return r.json()["access_token"], email, pw
        if r.status_code == 429:
            time.sleep(7)
            continue
        pytest.fail(f"register failed {r.status_code} {r.text}")
    pytest.fail("rate-limited register")


def H(tok): return {"Authorization": f"Bearer {tok}"}


# ============ PREDICTION ENGINE ============
class TestPrediction:
    def test_insufficient_data_no_500(self, user):
        tok, *_ = user
        r = requests.get(f"{BASE}/dashboard", headers=H(tok))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["prediction"]["has_data"] is False
        assert body["prediction"].get("avg_cycle_length") == 28

    def test_one_cycle_safe_defaults(self, user):
        tok, *_ = user
        # one cycle = no gaps -> avg_cycle defaults to 28
        c = (date.today() - timedelta(days=10)).isoformat()
        rr = requests.post(f"{BASE}/cycles", headers=H(tok), json={"start_date": c})
        assert rr.status_code == 200
        d = requests.get(f"{BASE}/dashboard", headers=H(tok)).json()
        assert d["prediction"]["has_data"] is True
        assert d["prediction"]["avg_cycle_length"] == 28
        assert d["prediction"]["cycle_day"] == 11

    def test_regular_28_day_cycles(self):
        # Fresh user
        email, pw = _u(), "Password123!"
        for _ in range(4):
            r = requests.post(f"{BASE}/auth/register",
                              json={"email": email, "password": pw})
            if r.status_code == 201:
                break
            time.sleep(7)
        tok = r.json()["access_token"]
        # seed 4 cycles 28d apart, last one 28 days ago
        starts = [(date.today() - timedelta(days=28*i)).isoformat()
                  for i in range(4, 0, -1)]
        for s in starts:
            assert requests.post(f"{BASE}/cycles", headers=H(tok),
                                 json={"start_date": s}).status_code == 200
        p = requests.get(f"{BASE}/dashboard", headers=H(tok)).json()["prediction"]
        assert p["avg_cycle_length"] == 28
        last_start = date.fromisoformat(p["last_period_start"])
        nxt = date.fromisoformat(p["next_period_date"])
        ov = date.fromisoformat(p["ovulation_date"])
        fs = date.fromisoformat(p["fertile_window_start"])
        fe = date.fromisoformat(p["fertile_window_end"])
        assert (nxt - last_start).days == 28
        assert (nxt - ov).days == 14
        assert (ov - fs).days == 5
        assert (fe - ov).days == 1

    def test_outlier_excluded(self):
        # Outlier 60d cycle should be excluded; remaining 28d cycles yield avg 28
        email, pw = _u(), "Password123!"
        for _ in range(4):
            r = requests.post(f"{BASE}/auth/register",
                              json={"email": email, "password": pw})
            if r.status_code == 201:
                break
            time.sleep(7)
        tok = r.json()["access_token"]
        today = date.today()
        # gaps: 60 (outlier), 28, 28, 28 -> avg 28
        starts = [
            today - timedelta(days=144),
            today - timedelta(days=84),   # gap 60 (outlier)
            today - timedelta(days=56),   # gap 28
            today - timedelta(days=28),   # gap 28
            today - timedelta(days=0),    # gap 28
        ]
        for s in starts:
            requests.post(f"{BASE}/cycles", headers=H(tok),
                          json={"start_date": s.isoformat()})
        p = requests.get(f"{BASE}/dashboard", headers=H(tok)).json()["prediction"]
        # average of [60,28,28,28] valid is [28,28,28] -> 28
        assert p["avg_cycle_length"] == 28, f"got {p['avg_cycle_length']}"


# ============ SYMPTOMS / MOODS / NOTES (daily_logs) ============
class TestLogs:
    def test_create_edit_delete_symptom(self, user):
        tok, *_ = user
        d = date.today().isoformat()
        # create
        r = requests.post(f"{BASE}/logs", headers=H(tok), json={
            "date": d,
            "symptoms": [{"name": "Cramps", "severity": "mild"},
                         {"name": "MyCustom", "severity": "moderate"}],
            "moods": ["Happy", "Calm"],
            "note": "feel ok",
            "tags": ["wfh"],
            "visibility": "private",
        })
        assert r.status_code == 200
        # read
        got = requests.get(f"{BASE}/logs/{d}", headers=H(tok)).json()
        assert len(got["symptoms"]) == 2
        names = {s["name"] for s in got["symptoms"]}
        assert "MyCustom" in names and "Cramps" in names
        assert "Happy" in got["moods"]
        assert got["note"] == "feel ok"
        # edit severity (upsert)
        requests.post(f"{BASE}/logs", headers=H(tok), json={
            "date": d,
            "symptoms": [{"name": "Cramps", "severity": "severe"}],
            "moods": ["Happy"],
            "note": "updated",
        })
        got2 = requests.get(f"{BASE}/logs/{d}", headers=H(tok)).json()
        assert got2["symptoms"][0]["severity"] == "severe"
        assert got2["note"] == "updated"
        # delete symptom by emptying
        requests.post(f"{BASE}/logs", headers=H(tok), json={
            "date": d, "symptoms": [], "moods": [], "note": ""})
        got3 = requests.get(f"{BASE}/logs/{d}", headers=H(tok)).json()
        assert got3["symptoms"] == [] and got3["moods"] == []

    def test_analytics_mood_frequency(self, user):
        tok, *_ = user
        # log a few days
        for i, mood in enumerate(["Happy", "Happy", "Tired"]):
            d = (date.today() - timedelta(days=i+1)).isoformat()
            requests.post(f"{BASE}/logs", headers=H(tok), json={
                "date": d, "symptoms": [], "moods": [mood], "note": ""})
        a = requests.get(f"{BASE}/analytics", headers=H(tok)).json()
        mf = {m["name"]: m["count"] for m in a.get("mood_frequency", [])}
        assert mf.get("Happy", 0) >= 2

    def test_health_event_symptom_crud_and_cross_user(self, user):
        tok, *_ = user
        ts = datetime.utcnow().isoformat() + "Z"
        d = ts[:10]
        r = requests.post(f"{BASE}/health-events", headers=H(tok), json={
            "event_type": "symptom", "timestamp": ts, "date": d,
            "data": {"name": "Cramps", "severity": "mild"}})
        assert r.status_code == 200
        eid = r.json()["id"]
        # list - present
        lst = requests.get(f"{BASE}/health-events?event_type=symptom",
                           headers=H(tok)).json()
        assert any(e["id"] == eid for e in lst)
        # cross-user 404
        email, pw = _u(), "Password123!"
        for _ in range(3):
            rr = requests.post(f"{BASE}/auth/register",
                               json={"email": email, "password": pw})
            if rr.status_code == 201:
                break
            time.sleep(7)
        other = rr.json()["access_token"]
        assert requests.get(f"{BASE}/health-events/{eid}",
                            headers=H(other)).status_code == 404
        # delete + verify soft-delete excludes
        assert requests.delete(f"{BASE}/health-events/{eid}",
                               headers=H(tok)).status_code == 200
        lst2 = requests.get(f"{BASE}/health-events?event_type=symptom",
                            headers=H(tok)).json()
        assert not any(e["id"] == eid for e in lst2)


# ============ HYDRATION ============
class TestHydration:
    def test_water_log_today_goal(self, user):
        tok, *_ = user
        # set goal
        r = requests.put(f"{BASE}/water/goal", headers=H(tok),
                         json={"goal_ml": 2000})
        assert r.status_code == 200
        # log a custom amount
        requests.post(f"{BASE}/water", headers=H(tok), json={"amount_ml": 500})
        requests.post(f"{BASE}/water", headers=H(tok), json={"amount_ml": 250})
        today = requests.get(f"{BASE}/water/today", headers=H(tok)).json()
        assert today["total_ml"] >= 750
        assert today["goal_ml"] == 2000
        # progress
        assert today["percentage"] >= 37
        # update goal -> progress recalcs
        requests.put(f"{BASE}/water/goal", headers=H(tok), json={"goal_ml": 1500})
        today2 = requests.get(f"{BASE}/water/today", headers=H(tok)).json()
        assert today2["goal_ml"] == 1500
        assert today2["percentage"] > today["percentage"]
        # analytics
        a = requests.get(f"{BASE}/water/analytics?days=7", headers=H(tok))
        assert a.status_code == 200
        assert "history" in a.json() and "avg_daily_ml" in a.json()


# ============ MEALS ============
class TestMeals:
    def test_meals_log_and_today(self, user):
        tok, *_ = user
        for mt, st in [("breakfast", "completed"), ("lunch", "skipped"),
                       ("dinner", "completed"), ("snack", "completed")]:
            r = requests.post(f"{BASE}/meals", headers=H(tok),
                              json={"meal_type": mt, "status": st})
            assert r.status_code == 200
        today = requests.get(f"{BASE}/meals/today", headers=H(tok)).json()
        assert today["completed_count"] >= 3
        assert today["skipped_count"] >= 1


# ============ SEXUAL ACTIVITY + PRIVACY GATING ============
class TestSexualActivityPrivacy:
    def test_log_and_partner_gating(self, user):
        tok_owner, owner_email, _ = user
        # owner logs activity
        r = requests.post(f"{BASE}/sexual-activity", headers=H(tok_owner),
                          json={"protection_used": True, "partner_present": True,
                                "share_with_partner": False})
        assert r.status_code == 200
        hist = requests.get(f"{BASE}/sexual-activity/history",
                            headers=H(tok_owner)).json()
        assert hist["total_entries"] >= 1

        # Create partner user + link
        email, pw = _u(), "Password123!"
        for _ in range(3):
            rr = requests.post(f"{BASE}/auth/register",
                               json={"email": email, "password": pw})
            if rr.status_code == 201:
                break
            time.sleep(7)
        partner_tok = rr.json()["access_token"]

        inv = requests.post(f"{BASE}/partner/invite",
                            headers=H(tok_owner)).json()
        link_id, token = inv["id"], inv["token"]
        assert requests.post(f"{BASE}/partner/accept", headers=H(partner_tok),
                             json={"token": token}).status_code == 200

        # activity flag default False -> intimacy must be None / hidden
        view = requests.get(f"{BASE}/partner/view/{link_id}",
                            headers=H(partner_tok)).json()
        assert view.get("intimacy") is None, f"intimacy leaked with flag off: {view.get('intimacy')}"

        # Owner enables activity flag
        perms = {"periods": True, "fertility": True, "symptoms": True,
                 "moods": True, "notes": True, "hydration": True,
                 "meals": True, "medications": True, "activity": True,
                 "timeline": True, "digest": True}
        upd = requests.put(f"{BASE}/partner/links/{link_id}/permissions",
                           headers=H(tok_owner), json=perms)
        assert upd.status_code == 200
        view2 = requests.get(f"{BASE}/partner/view/{link_id}",
                             headers=H(partner_tok)).json()
        assert view2.get("intimacy") is not None
        assert view2["intimacy"]["count"] >= 1


# ============ MEDICATIONS ============
class TestMedications:
    def test_schedule_take_adherence(self, user):
        tok, *_ = user
        # painkiller daily
        r = requests.post(f"{BASE}/medication-schedules", headers=H(tok), json={
            "name": "TestPain", "dosage": "200mg", "category": "painkiller",
            "schedule_type": "daily", "times": ["08:00", "20:00"], "enabled": True})
        assert r.status_code == 200, r.text
        sid = r.json()["id"]
        # vitamin
        rv = requests.post(f"{BASE}/medication-schedules", headers=H(tok), json={
            "name": "TestVit", "category": "vitamin",
            "schedule_type": "daily", "times": ["09:00"], "enabled": True})
        assert rv.status_code == 200
        # today
        td = requests.get(f"{BASE}/medication-schedules/today",
                          headers=H(tok)).json()
        assert td["total"] >= 3
        # take one
        t = requests.post(f"{BASE}/medication-schedules/{sid}/take",
                          headers=H(tok), json={"scheduled_time": "08:00"})
        assert t.status_code == 200
        # adherence
        ad = requests.get(f"{BASE}/medication-schedules/adherence?days=7",
                          headers=H(tok)).json()
        assert ad["has_data"] is True
        assert ad["taken_total"] >= 1
        # update
        u = requests.put(f"{BASE}/medication-schedules/{sid}", headers=H(tok),
                        json={"name": "TestPain2", "dosage": "400mg",
                              "category": "painkiller", "schedule_type": "daily",
                              "times": ["08:00"], "enabled": True})
        assert u.status_code == 200
        # delete
        d = requests.delete(f"{BASE}/medication-schedules/{sid}",
                            headers=H(tok))
        assert d.status_code == 200
        # cross-user 404
        email, pw = _u(), "Password123!"
        for _ in range(3):
            rr = requests.post(f"{BASE}/auth/register",
                               json={"email": email, "password": pw})
            if rr.status_code == 201:
                break
            time.sleep(7)
        other = rr.json()["access_token"]
        assert requests.delete(f"{BASE}/medication-schedules/{sid}",
                               headers=H(other)).status_code == 404

    def test_medications_log_history(self, user):
        tok, *_ = user
        r = requests.post(f"{BASE}/medications", headers=H(tok), json={
            "name": "BCpill", "dosage": "1 tablet", "category": "birth_control"})
        assert r.status_code == 200
        h = requests.get(f"{BASE}/medications/history",
                         headers=H(tok)).json()
        assert h["total_entries"] >= 1


# ============ DAILY / WIDGET SUMMARY ============
class TestSummaries:
    def test_daily_summary_no_500(self, user):
        tok, *_ = user
        r = requests.get(f"{BASE}/daily-summary", headers=H(tok))
        assert r.status_code == 200, r.text
        b = r.json()
        assert "headline" in b and "lines" in b

    def test_widget_summary_no_500(self, user):
        tok, *_ = user
        r = requests.get(f"{BASE}/widget-summary", headers=H(tok))
        assert r.status_code == 200, r.text
        b = r.json()
        for k in ("prediction", "hydration", "hydration_goal", "meals_logged",
                  "medications_taken", "streak_days"):
            assert k in b


# ============ NOTES via health-events + search ============
class TestNotes:
    def test_note_search_visibility(self, user):
        tok, *_ = user
        marker = "QA2_NOTE_" + uuid.uuid4().hex[:6]
        ts = datetime.utcnow().isoformat() + "Z"
        r = requests.post(f"{BASE}/health-events", headers=H(tok), json={
            "event_type": "note", "timestamp": ts, "date": ts[:10],
            "data": {}, "note": f"my private {marker}",
            "visibility": "private", "tags": ["journal"]})
        assert r.status_code == 200
        # search
        s = requests.get(f"{BASE}/search?q={marker}", headers=H(tok)).json()
        assert s["count"] >= 1
        assert any(marker in (r.get("note") or "") for r in s["results"])
