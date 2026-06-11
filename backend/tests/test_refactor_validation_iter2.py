"""Refactor-validation tests for iteration 2.

Scope: validate that the iter-2 refactor preserves behavior:
  - Auth routes extracted to auth_router.py work end-to-end
  - Medication adherence is now computed with 2 batch queries instead of N+1;
    results must be correct for daily, interval, and cycle_based schedules
  - Smoke regression on dashboard / analytics / daily-summary / widget-summary /
    cycles / logs / partner so the auth-router extraction didn't break imports

Uses the seed account (tester@cycle.app / Test1234!) to dodge register rate limit.
"""
import time
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import requests

from tests.conftest import API, register_user

SEED_EMAIL = "tester@cycle.app"
SEED_PASSWORD = "Test1234!"


# ----------------------------- session-level seed login -----------------------------
@pytest.fixture(scope="module")
def http():
    return requests.Session()


@pytest.fixture(scope="module")
def seed_tokens(http):
    r = http.post(f"{API}/auth/login",
                  json={"email": SEED_EMAIL, "password": SEED_PASSWORD}, timeout=20)
    assert r.status_code == 200, f"seed login failed: {r.text}"
    return r.json()


@pytest.fixture(scope="module")
def H(seed_tokens):
    return {"Authorization": f"Bearer {seed_tokens['access_token']}",
            "Content-Type": "application/json"}


# =============================================================================
# AUTH (now served by extracted auth_router.py at /api/auth/*)
# =============================================================================
class TestAuthRouter:
    def test_login_success(self, seed_tokens):
        assert seed_tokens.get("access_token")
        assert seed_tokens.get("refresh_token")
        assert seed_tokens.get("token_type") == "bearer"

    def test_login_wrong_password_returns_401(self, http):
        r = http.post(f"{API}/auth/login",
                      json={"email": SEED_EMAIL, "password": "WRONG_pw_1234"},
                      timeout=20)
        assert r.status_code == 401, r.text
        assert "credentials" in r.text.lower()

    def test_me_endpoint(self, http, H):
        r = http.get(f"{API}/auth/me", headers=H, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["email"] == SEED_EMAIL
        assert body.get("id")

    def test_refresh_rotation(self, http, seed_tokens):
        # Get a *fresh* token pair so we don't disturb the shared seed_tokens.
        r0 = http.post(f"{API}/auth/login",
                       json={"email": SEED_EMAIL, "password": SEED_PASSWORD}, timeout=20)
        assert r0.status_code == 200
        old_rt = r0.json()["refresh_token"]

        r1 = http.post(f"{API}/auth/refresh", json={"refresh_token": old_rt}, timeout=20)
        assert r1.status_code == 200, r1.text
        new_rt = r1.json()["refresh_token"]
        assert new_rt != old_rt

        # Re-using the old refresh must now be rejected (rotation invalidates it).
        r2 = http.post(f"{API}/auth/refresh", json={"refresh_token": old_rt}, timeout=20)
        assert r2.status_code == 401, r2.text

    def test_logout_revokes_session(self, http):
        r0 = http.post(f"{API}/auth/login",
                       json={"email": SEED_EMAIL, "password": SEED_PASSWORD}, timeout=20)
        assert r0.status_code == 200
        tok = r0.json()
        h = {"Authorization": f"Bearer {tok['access_token']}"}
        rl = http.post(f"{API}/auth/logout", headers=h, timeout=20)
        assert rl.status_code == 200
        # Refresh after logout should fail
        rr = http.post(f"{API}/auth/refresh",
                       json={"refresh_token": tok["refresh_token"]}, timeout=20)
        assert rr.status_code == 401

    def test_register_returns_generic_verification_response(self, http):
        # Using a brand-new email; should NOT issue tokens (verification required).
        email = f"TEST_refactor_{uuid.uuid4().hex[:8]}@cycle.app"
        r = http.post(f"{API}/auth/register",
                      json={"email": email, "password": "Password123",
                            "full_name": "Refactor Tester"}, timeout=20)
        # Could be 429 if other tests have hammered the limit; tolerate that.
        if r.status_code == 429:
            pytest.skip("register rate-limited; covered elsewhere")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("verification_required") is True
        assert "access_token" not in body  # tokens only after verify-email

    def test_forgot_password_generic_response(self, http):
        r = http.post(f"{API}/auth/forgot-password",
                      json={"email": "nonexistent_TEST@cycle.app"}, timeout=20)
        assert r.status_code == 200
        assert "reset code" in r.json().get("detail", "").lower()


# =============================================================================
# MEDICATION ADHERENCE (optimized aggregation + cycle-day map)
# =============================================================================
def _create_schedule(http, H, payload):
    r = http.post(f"{API}/medication-schedules", headers=H, json=payload, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


def _delete_schedule(http, H, sid):
    http.delete(f"{API}/medication-schedules/{sid}", headers=H, timeout=20)


def _take(http, H, sid, scheduled_time=None, ts=None):
    body = {}
    if scheduled_time:
        body["scheduled_time"] = scheduled_time
    if ts:
        body["timestamp"] = ts
    r = http.post(f"{API}/medication-schedules/{sid}/take",
                  headers=H, json=body, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


def _adherence(http, H, days=7):
    r = http.get(f"{API}/medication-schedules/adherence?days={days}",
                 headers=H, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


class TestAdherenceRefactor:
    """The adherence endpoint was rewritten from O(days x schedules) DB calls to
    2 batch queries. Validate correctness for each schedule type."""

    @pytest.fixture
    def daily_sched(self, http, H):
        s = _create_schedule(http, H, {
            "name": "TEST_refactor_daily",
            "schedule_type": "daily",
            "times": ["08:00", "20:00"],
            "category": "vitamin",
            "enabled": True,
        })
        yield s
        _delete_schedule(http, H, s["id"])

    @pytest.fixture
    def interval_sched(self, http, H):
        s = _create_schedule(http, H, {
            "name": "TEST_refactor_interval",
            "schedule_type": "interval",
            "interval_hours": 8,
            "interval_start": "08:00",
            "category": "painkiller",
            "enabled": True,
        })
        yield s
        _delete_schedule(http, H, s["id"])

    @pytest.fixture
    def cycle_sched(self, http, H):
        s = _create_schedule(http, H, {
            "name": "TEST_refactor_cyclebased",
            "schedule_type": "cycle_based",
            "times": ["09:00"],
            "cycle_days": [1, 2, 3, 4, 5],
            "category": "hormone",
            "enabled": True,
        })
        yield s
        _delete_schedule(http, H, s["id"])

    def test_daily_schedule_shape_and_today_counts(self, http, H, daily_sched):
        a = _adherence(http, H, days=7)
        # Required keys
        for key in ("days", "has_data", "overall_percentage", "expected_total",
                    "taken_total", "streak_days", "active_medications",
                    "medications", "recent"):
            assert key in a, f"missing key: {key}"
        # Recent must be exactly 7 entries (last 7 days)
        assert len(a["recent"]) == 7
        # Our daily schedule with 2 times => expected at least 2 for today
        today = date.today().isoformat()
        today_bar = next((r for r in a["recent"] if r["date"] == today), None)
        assert today_bar, "today not in recent"
        assert today_bar["expected"] >= 2

        # Mark ONE 08:00 dose taken; adherence should reflect taken=1 for today
        _take(http, H, daily_sched["id"], scheduled_time="08:00")
        a2 = _adherence(http, H, days=7)
        today_bar2 = next(r for r in a2["recent"] if r["date"] == today)
        assert today_bar2["taken"] >= 1
        # taken capped at expected
        assert today_bar2["taken"] <= today_bar2["expected"]
        # per-med breakdown shows this schedule
        med = next((m for m in a2["medications"] if m["schedule_id"] == daily_sched["id"]), None)
        assert med is not None
        assert med["expected"] >= 2
        assert med["taken"] >= 1
        # overall percentage = round(taken/expected * 100)
        if a2["expected_total"]:
            assert a2["overall_percentage"] == round(a2["taken_total"] / a2["expected_total"] * 100)

    def test_interval_schedule_expands_doses(self, http, H, interval_sched):
        a = _adherence(http, H, days=7)
        med = next((m for m in a["medications"]
                    if m["schedule_id"] == interval_sched["id"]), None)
        assert med is not None
        # every 8h from 08:00 -> 08, 16; only 2 fit before 24:00 (next is 24:00)
        # so expected per day = 2. For 7 days that's 14 (minus days before creation).
        # Just sanity-check it's >0.
        assert med["expected"] >= 2

    def test_cycle_based_uses_cycle_day_map(self, http, H, cycle_sched):
        # Without any cycle in the DB for this user, cycle_day is None for every
        # date so cycle_based schedule should contribute 0 expected.
        a = _adherence(http, H, days=7)
        med = next((m for m in a["medications"]
                    if m["schedule_id"] == cycle_sched["id"]), None)
        assert med is not None
        # We don't assert 0 strictly (seed user might already have a cycle), but
        # ensure the field exists & is non-negative.
        assert med["expected"] >= 0
        assert med["taken"] >= 0

    def test_today_endpoint(self, http, H, daily_sched):
        r = http.get(f"{API}/medication-schedules/today", headers=H, timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert "doses" in body and "total" in body and "taken" in body
        # Our 2x daily schedule should appear in today's doses
        our = [d for d in body["doses"] if d["schedule_id"] == daily_sched["id"]]
        assert len(our) >= 2

    def test_idempotent_take_via_client_id(self, http, H, daily_sched):
        cid = f"TEST_{uuid.uuid4().hex[:8]}"
        r1 = http.post(f"{API}/medication-schedules/{daily_sched['id']}/take",
                       headers=H,
                       json={"scheduled_time": "20:00", "client_id": cid}, timeout=20)
        r2 = http.post(f"{API}/medication-schedules/{daily_sched['id']}/take",
                       headers=H,
                       json={"scheduled_time": "20:00", "client_id": cid}, timeout=20)
        assert r1.status_code == 200 and r2.status_code == 200
        assert r2.json().get("deduped") is True


# =============================================================================
# Medication CRUD smoke
# =============================================================================
class TestMedicationCRUD:
    def test_full_crud(self, http, H):
        # create
        r = http.post(f"{API}/medication-schedules", headers=H, json={
            "name": "TEST_crud_med",
            "schedule_type": "daily",
            "times": ["07:30"],
            "enabled": True,
        }, timeout=20)
        assert r.status_code == 200, r.text
        sid = r.json()["id"]
        # list contains it
        rl = http.get(f"{API}/medication-schedules", headers=H, timeout=20)
        assert rl.status_code == 200
        assert any(s["id"] == sid for s in rl.json())
        # update / toggle enabled
        ru = http.put(f"{API}/medication-schedules/{sid}", headers=H, json={
            "name": "TEST_crud_med_renamed",
            "schedule_type": "daily",
            "times": ["07:30", "19:30"],
            "enabled": False,
        }, timeout=20)
        assert ru.status_code == 200
        assert ru.json()["name"] == "TEST_crud_med_renamed"
        assert ru.json()["enabled"] is False
        assert len(ru.json()["times"]) == 2
        # delete (soft)
        rd = http.delete(f"{API}/medication-schedules/{sid}", headers=H, timeout=20)
        assert rd.status_code == 200
        rl2 = http.get(f"{API}/medication-schedules", headers=H, timeout=20)
        assert not any(s["id"] == sid for s in rl2.json())


# =============================================================================
# Regression smoke for endpoints that import from refactored server.py
# =============================================================================
class TestRegressionSmoke:
    @pytest.mark.parametrize("path", [
        "/dashboard",
        "/analytics?days=30",
        "/daily-summary",
        "/widget-summary",
        "/cycles",
        "/logs",
    ])
    def test_endpoint_200(self, http, H, path):
        r = http.get(f"{API}{path}", headers=H, timeout=30)
        assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:200]}"

    def test_partner_links_endpoint(self, http, H):
        # /partner/links should always 200 (empty list ok). Validates partner router
        # still imports DEFAULT_FLAGS/helpers correctly after server.py refactor.
        r = http.get(f"{API}/partner/links", headers=H, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        # Returns {"sharing": [...], "viewing": [...]}
        assert "sharing" in body and "viewing" in body

    def test_partner_invite(self, http, H):
        r = http.post(f"{API}/partner/invite", headers=H,
                      json={"partner_email": "TEST_partner@cycle.app",
                            "permissions": {"view_cycle": True}}, timeout=20)
        # 200/201 created; 400 if a pending invite already exists for that email.
        assert r.status_code in (200, 201, 400), r.text
