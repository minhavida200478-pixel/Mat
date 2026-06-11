"""Cycle Health backend API test suite — auth, cycles, logs, dashboard,
analytics, and partner-sharing privacy enforcement."""
import time
import uuid
from datetime import date, timedelta

import pytest
import requests

from tests.conftest import API


# -------------------- Auth --------------------
class TestAuth:
    def test_register_returns_token_pair(self, client):
        email = f"TEST_reg_{uuid.uuid4().hex[:8]}@cycle.app"
        r = client.post(f"{API}/auth/register",
                        json={"email": email, "password": "Password123",
                              "full_name": "Reg User"}, timeout=20)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"] and body["refresh_token"]

    def test_register_short_password_rejected(self, client):
        r = client.post(f"{API}/auth/register",
                        json={"email": f"TEST_short_{uuid.uuid4().hex[:6]}@cycle.app",
                              "password": "short"}, timeout=20)
        assert r.status_code == 422

    def test_register_duplicate_email(self, client, fresh_user):
        r = client.post(f"{API}/auth/register",
                        json={"email": fresh_user["email"],
                              "password": "Password123"}, timeout=20)
        assert r.status_code == 400

    def test_login_success_and_me(self, client, fresh_user):
        r = client.post(f"{API}/auth/login",
                        json={"email": fresh_user["email"],
                              "password": fresh_user["password"]}, timeout=20)
        assert r.status_code == 200
        tokens = r.json()
        me = client.get(f"{API}/auth/me",
                        headers={"Authorization": f"Bearer {tokens['access_token']}"},
                        timeout=20)
        assert me.status_code == 200
        assert me.json()["email"] == fresh_user["email"].lower()

    def test_login_invalid_credentials(self, client, fresh_user):
        r = client.post(f"{API}/auth/login",
                        json={"email": fresh_user["email"],
                              "password": "WrongPass123"}, timeout=20)
        assert r.status_code == 401

    def test_brute_force_lockout_after_5_fails(self, client):
        # Create a dedicated user so we can hammer it without affecting others.
        email = f"TEST_lock_{uuid.uuid4().hex[:8]}@cycle.app"
        client.post(f"{API}/auth/register",
                    json={"email": email, "password": "Password123"}, timeout=20)
        last_status = None
        for _ in range(5):
            r = client.post(f"{API}/auth/login",
                            json={"email": email, "password": "WrongOne1"}, timeout=20)
            last_status = r.status_code
        # 6th attempt (even with right password) should be locked
        r = client.post(f"{API}/auth/login",
                        json={"email": email, "password": "Password123"}, timeout=20)
        assert r.status_code == 429, f"Expected 429 lockout, got {r.status_code} (5th={last_status})"


# -------------------- Refresh rotation --------------------
class TestRefresh:
    def test_refresh_rotation_and_reuse_detection(self, client, fresh_user):
        original = fresh_user["refresh_token"]
        # First refresh should succeed and rotate
        r1 = client.post(f"{API}/auth/refresh",
                         json={"refresh_token": original}, timeout=20)
        assert r1.status_code == 200, r1.text
        new_pair = r1.json()
        assert new_pair["refresh_token"] != original

        # Reusing the original should fail (reuse detection)
        r2 = client.post(f"{API}/auth/refresh",
                         json={"refresh_token": original}, timeout=20)
        assert r2.status_code == 401

        # Even the new token should now be revoked (family invalidation)
        r3 = client.post(f"{API}/auth/refresh",
                         json={"refresh_token": new_pair["refresh_token"]}, timeout=20)
        assert r3.status_code == 401


# -------------------- Cycles CRUD --------------------
class TestCycles:
    def test_full_cycle_crud(self, client, auth_headers):
        today = date.today()
        payload = {"start_date": (today - timedelta(days=30)).isoformat(),
                   "end_date": (today - timedelta(days=25)).isoformat()}
        # Create
        c = client.post(f"{API}/cycles", json=payload, headers=auth_headers, timeout=20)
        assert c.status_code == 200, c.text
        cid = c.json()["id"]
        # is UUID
        uuid.UUID(cid)

        # List → present
        l = client.get(f"{API}/cycles", headers=auth_headers, timeout=20)
        assert l.status_code == 200
        ids = [r["id"] for r in l.json()]
        assert cid in ids

        # Update
        new_end = (today - timedelta(days=24)).isoformat()
        u = client.put(f"{API}/cycles/{cid}", json={"end_date": new_end},
                       headers=auth_headers, timeout=20)
        assert u.status_code == 200
        # Verify
        l2 = client.get(f"{API}/cycles", headers=auth_headers, timeout=20)
        row = next(r for r in l2.json() if r["id"] == cid)
        assert row["end_date"] == new_end

        # Delete (soft)
        d = client.delete(f"{API}/cycles/{cid}", headers=auth_headers, timeout=20)
        assert d.status_code == 200
        l3 = client.get(f"{API}/cycles", headers=auth_headers, timeout=20)
        assert cid not in [r["id"] for r in l3.json()]


# -------------------- Daily logs --------------------
class TestLogs:
    def test_upsert_and_fetch_log(self, client, auth_headers):
        today_str = date.today().isoformat()
        payload = {
            "date": today_str,
            "symptoms": [{"name": "cramps", "severity": "moderate"}],
            "moods": ["calm"],
            "note": "TEST note",
            "tags": ["sleep"],
            "visibility": "private",
        }
        r = client.post(f"{API}/logs", json=payload, headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text

        # Upsert same date with new values
        payload["moods"] = ["happy"]
        r2 = client.post(f"{API}/logs", json=payload, headers=auth_headers, timeout=20)
        assert r2.status_code == 200

        # GET single date
        g = client.get(f"{API}/logs/{today_str}", headers=auth_headers, timeout=20)
        assert g.status_code == 200
        body = g.json()
        assert body["moods"] == ["happy"]
        assert body["symptoms"][0]["name"] == "cramps"

        # GET list
        gl = client.get(f"{API}/logs", headers=auth_headers, timeout=20)
        assert gl.status_code == 200
        dates = [x["date"] for x in gl.json()]
        assert today_str in dates


# -------------------- Dashboard + analytics --------------------
class TestDashboardAnalytics:
    def _seed_cycles(self, client, headers):
        today = date.today()
        starts = [today - timedelta(days=84),
                  today - timedelta(days=56),
                  today - timedelta(days=28)]
        for s in starts:
            payload = {"start_date": s.isoformat(),
                       "end_date": (s + timedelta(days=4)).isoformat()}
            r = client.post(f"{API}/cycles", json=payload, headers=headers, timeout=20)
            assert r.status_code == 200

    def test_dashboard_prediction(self, client, auth_headers):
        self._seed_cycles(client, auth_headers)
        r = client.get(f"{API}/dashboard", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        pred = r.json()["prediction"]
        for k in ("cycle_day", "next_period_date", "ovulation_date",
                  "fertile_window_start", "fertile_window_end"):
            assert k in pred, f"missing prediction key {k}"
        assert pred["avg_cycle_length"] == 28

    def test_analytics_payload(self, client, auth_headers):
        self._seed_cycles(client, auth_headers)
        # add a log to populate symptom_frequency
        client.post(f"{API}/logs",
                    json={"date": date.today().isoformat(),
                          "symptoms": [{"name": "headache", "severity": "mild"}],
                          "moods": ["tired"], "note": "", "tags": [],
                          "visibility": "private"},
                    headers=auth_headers, timeout=20)
        r = client.get(f"{API}/analytics", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert body["avg_cycle_length"] == 28.0
        assert body["regularity_score"] == 100
        names = [s["name"] for s in body["symptom_frequency"]]
        assert "headache" in names


# -------------------- Partner sharing privacy enforcement --------------------
class TestPartnerSharing:
    def _register(self, client, prefix):
        email = f"TEST_{prefix}_{uuid.uuid4().hex[:8]}@cycle.app"
        r = client.post(f"{API}/auth/register",
                        json={"email": email, "password": "Password123",
                              "full_name": prefix.title()}, timeout=20)
        assert r.status_code == 201
        return email, r.json()["access_token"]

    def test_invite_accept_view_with_flag_strip(self, client):
        # User A (owner) and User B (partner)
        a_email, a_tok = self._register(client, "owner")
        b_email, b_tok = self._register(client, "partner")
        h_a = {"Authorization": f"Bearer {a_tok}", "Content-Type": "application/json"}
        h_b = {"Authorization": f"Bearer {b_tok}", "Content-Type": "application/json"}

        # Seed owner data
        today = date.today()
        for s in (today - timedelta(days=56), today - timedelta(days=28)):
            client.post(f"{API}/cycles",
                        json={"start_date": s.isoformat(),
                              "end_date": (s + timedelta(days=4)).isoformat()},
                        headers=h_a, timeout=20)
        client.post(f"{API}/logs",
                    json={"date": today.isoformat(),
                          "symptoms": [{"name": "cramps", "severity": "mild"}],
                          "moods": ["happy"], "note": "shared note",
                          "tags": [], "visibility": "shared"},
                    headers=h_a, timeout=20)

        # Invite + accept
        inv = client.post(f"{API}/partner/invite", headers=h_a, timeout=20)
        assert inv.status_code == 200
        token = inv.json()["token"]
        link_id = inv.json()["id"]

        acc = client.post(f"{API}/partner/accept",
                          json={"token": token}, headers=h_b, timeout=20)
        assert acc.status_code == 200, acc.text

        # Initially all flags on — partner sees symptoms/moods/notes
        v = client.get(f"{API}/partner/view/{link_id}", headers=h_b, timeout=20)
        assert v.status_code == 200
        body = v.json()
        assert body["prediction"] is not None
        assert len(body["logs"]) == 1
        e = body["logs"][0]
        assert "symptoms" in e and "moods" in e and "note" in e

        # Turn OFF symptoms flag
        perms = {"periods": True, "fertility": True, "symptoms": False,
                 "moods": True, "notes": True}
        u = client.put(f"{API}/partner/links/{link_id}/permissions",
                       json=perms, headers=h_a, timeout=20)
        assert u.status_code == 200

        # Partner view should no longer include 'symptoms'
        v2 = client.get(f"{API}/partner/view/{link_id}", headers=h_b, timeout=20)
        assert v2.status_code == 200
        e2 = v2.json()["logs"][0]
        assert "symptoms" not in e2, f"symptoms leaked: {e2}"
        assert "moods" in e2 and "note" in e2

        # Turn OFF fertility flag — fertility keys should disappear from prediction
        perms2 = {"periods": True, "fertility": False, "symptoms": False,
                  "moods": True, "notes": True}
        client.put(f"{API}/partner/links/{link_id}/permissions",
                   json=perms2, headers=h_a, timeout=20)
        v3 = client.get(f"{API}/partner/view/{link_id}", headers=h_b, timeout=20)
        pred = v3.json()["prediction"]
        assert "ovulation_date" not in pred
        assert "fertile_window_start" not in pred
        assert "next_period_date" in pred  # periods still on

    def test_cannot_link_to_self(self, client):
        email, tok = self._register(client, "self")
        h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
        inv = client.post(f"{API}/partner/invite", headers=h, timeout=20)
        token = inv.json()["token"]
        r = client.post(f"{API}/partner/accept",
                        json={"token": token}, headers=h, timeout=20)
        assert r.status_code == 400
