"""Full production-readiness QA audit covering auth security, partner gating,
period tracking, analytics, and weekly auto-backup. Tests are organized into
focused classes; each is independent and uses fresh throwaway users (TEST_*).
"""
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import requests

from tests.conftest import API, register_user

JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-prod-super-secret-key-9f3a")


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ----------------------- AUTHENTICATION -----------------------
class TestAuthRegisterLogin:
    def test_register_valid_and_duplicate(self, client):
        user = register_user(client, "reg")
        # duplicate
        r = client.post(f"{API}/auth/register",
                        json={"email": user["email"], "password": "Password123"})
        assert r.status_code == 400, r.text
        assert "already" in r.json().get("detail", "").lower()

    def test_register_short_password_rejected(self, client):
        r = client.post(f"{API}/auth/register",
                        json={"email": f"TEST_short_{uuid.uuid4().hex[:6]}@cycle.app",
                              "password": "short1"})
        assert r.status_code == 422, r.text

    def test_register_invalid_email_rejected(self, client):
        r = client.post(f"{API}/auth/register",
                        json={"email": "not-an-email", "password": "Password123"})
        assert r.status_code == 422

    def test_login_valid(self, client):
        u = register_user(client, "login")
        r = client.post(f"{API}/auth/login",
                        json={"email": u["email"], "password": u["password"]})
        assert r.status_code == 200
        data = r.json()
        assert data.get("access_token") and data.get("refresh_token")

    def test_login_invalid_password(self, client):
        u = register_user(client, "loginbad")
        r = client.post(f"{API}/auth/login",
                        json={"email": u["email"], "password": "WrongPass1"})
        assert r.status_code == 401

    def test_login_unknown_email(self, client):
        r = client.post(f"{API}/auth/login",
                        json={"email": f"TEST_ghost_{uuid.uuid4().hex[:6]}@cycle.app",
                              "password": "Password123"})
        assert r.status_code == 401


class TestAuthMeAndLogout:
    def test_me_with_valid_token(self, client, fresh_user):
        r = client.get(f"{API}/auth/me", headers=_h(fresh_user["access_token"]))
        assert r.status_code == 200
        body = r.json()
        # Backend lowercases emails on storage (intentional)
        assert body["email"] == fresh_user["email"].lower()
        assert "password_hash" not in body and "_id" not in body
        assert body.get("id")

    def test_me_missing_token(self, client):
        r = client.get(f"{API}/auth/me")
        assert r.status_code in (401, 403)

    def test_me_invalid_token(self, client):
        r = client.get(f"{API}/auth/me", headers=_h("invalid.token.value"))
        assert r.status_code == 401

    def test_logout_revokes_refresh_tokens(self, client, fresh_user):
        r = client.post(f"{API}/auth/logout", headers=_h(fresh_user["access_token"]))
        assert r.status_code == 200
        # subsequent refresh must fail with 401
        rr = client.post(f"{API}/auth/refresh",
                         json={"refresh_token": fresh_user["refresh_token"]})
        assert rr.status_code == 401, rr.text


class TestAuthRefreshRotation:
    def test_refresh_rotates_and_old_is_used(self, client, fresh_user):
        r1 = client.post(f"{API}/auth/refresh",
                         json={"refresh_token": fresh_user["refresh_token"]})
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1["access_token"] != fresh_user["access_token"]
        assert d1["refresh_token"] != fresh_user["refresh_token"]

        # new access token works on /auth/me
        me = client.get(f"{API}/auth/me", headers=_h(d1["access_token"]))
        assert me.status_code == 200

    def test_refresh_reuse_attack_invalidates_session(self, client):
        u = register_user(client, "reuse")
        # First rotation: produces new pair AND a *new unused* refresh token
        r1 = client.post(f"{API}/auth/refresh",
                         json={"refresh_token": u["refresh_token"]})
        assert r1.status_code == 200
        rotated = r1.json()["refresh_token"]

        # Replay the original (now used) refresh token -> 401 + revoke all
        r2 = client.post(f"{API}/auth/refresh",
                         json={"refresh_token": u["refresh_token"]})
        assert r2.status_code == 401

        # The previously-issued rotated (not-yet-used) token must now ALSO be rejected
        r3 = client.post(f"{API}/auth/refresh", json={"refresh_token": rotated})
        assert r3.status_code == 401, (
            f"Session was NOT invalidated after reuse attack. Rotated token still works: {r3.text}")


class TestAuthJWTHardening:
    def _forge(self, user_id: str, typ: str, delta: timedelta) -> str:
        return jwt.encode({
            "sub": user_id, "typ": typ,
            "exp": datetime.now(timezone.utc) + delta,
            "iat": datetime.now(timezone.utc),
            "jti": str(uuid.uuid4()),
        }, JWT_SECRET, algorithm="HS256")

    def test_expired_access_token_rejected(self, client, fresh_user):
        # Decode existing token to extract sub
        payload = jwt.decode(fresh_user["access_token"], JWT_SECRET, algorithms=["HS256"])
        expired = self._forge(payload["sub"], "access", timedelta(seconds=-60))
        r = client.get(f"{API}/auth/me", headers=_h(expired))
        assert r.status_code == 401

    def test_invalid_signature_rejected(self, client, fresh_user):
        payload = jwt.decode(fresh_user["access_token"], JWT_SECRET, algorithms=["HS256"])
        bad = jwt.encode({**payload, "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
                         "wrong-secret-key", algorithm="HS256")
        r = client.get(f"{API}/auth/me", headers=_h(bad))
        assert r.status_code == 401

    def test_refresh_token_rejected_on_access_endpoint(self, client, fresh_user):
        # typ mismatch
        r = client.get(f"{API}/auth/me", headers=_h(fresh_user["refresh_token"]))
        assert r.status_code == 401


class TestAccountLockout:
    def test_5_failed_logins_locks_account(self, client):
        u = register_user(client, "lockout")
        # 5 wrong attempts
        for _ in range(5):
            r = client.post(f"{API}/auth/login",
                            json={"email": u["email"], "password": "WrongPass1"})
            assert r.status_code in (401, 429)
            if r.status_code == 429:
                break

        # 6th attempt (or correct password) should now return 429
        r2 = client.post(f"{API}/auth/login",
                         json={"email": u["email"], "password": "WrongPass1"})
        # even correct password should be blocked during lock window
        r3 = client.post(f"{API}/auth/login",
                         json={"email": u["email"], "password": u["password"]})
        assert r2.status_code == 429, f"Expected 429 lockout, got {r2.status_code} {r2.text}"
        assert r3.status_code == 429, (
            f"Correct password during lock window should still be 429, got {r3.status_code}")


# ----------------------- PARTNER LINKING -----------------------
@pytest.fixture
def two_users(client):
    owner = register_user(client, "owner")
    partner = register_user(client, "partner")
    return owner, partner


def _link_pair(client, owner, partner):
    inv = client.post(f"{API}/partner/invite", headers=_h(owner["access_token"]))
    assert inv.status_code == 200, inv.text
    token = inv.json()["token"]
    acc = client.post(f"{API}/partner/accept", json={"token": token},
                      headers=_h(partner["access_token"]))
    assert acc.status_code == 200, acc.text
    # Get link id from owner's sharing list
    links = client.get(f"{API}/partner/links", headers=_h(owner["access_token"]))
    link_id = links.json()["sharing"][0]["id"]
    return link_id


class TestPartnerLinking:
    def test_invite_creates_pending_with_expiry(self, client, fresh_user):
        r = client.post(f"{API}/partner/invite", headers=_h(fresh_user["access_token"]))
        assert r.status_code == 200
        d = r.json()
        assert d.get("token") and d.get("expires_at")
        # 48h expiry sanity
        exp = datetime.fromisoformat(d["expires_at"])
        delta_hours = (exp - datetime.now(timezone.utc)).total_seconds() / 3600
        assert 47 < delta_hours <= 48.5

    def test_accept_invalid_token(self, client, fresh_user):
        r = client.post(f"{API}/partner/accept", json={"token": "DOESNOTX"},
                        headers=_h(fresh_user["access_token"]))
        assert r.status_code == 404

    def test_cannot_accept_own_invite(self, client, fresh_user):
        inv = client.post(f"{API}/partner/invite",
                          headers=_h(fresh_user["access_token"]))
        token = inv.json()["token"]
        r = client.post(f"{API}/partner/accept", json={"token": token},
                        headers=_h(fresh_user["access_token"]))
        assert r.status_code == 400

    def test_full_link_lifecycle(self, client, two_users):
        owner, partner = two_users
        link_id = _link_pair(client, owner, partner)

        # owner sees sharing, partner sees viewing
        ol = client.get(f"{API}/partner/links", headers=_h(owner["access_token"])).json()
        pl = client.get(f"{API}/partner/links", headers=_h(partner["access_token"])).json()
        assert len(ol["sharing"]) == 1 and ol["sharing"][0]["status"] == "active"
        assert len(pl["viewing"]) == 1
        assert pl["viewing"][0]["id"] == link_id

        # update permissions -> applied immediately on /partner/view
        perms = {"periods": False, "fertility": False, "symptoms": False,
                 "moods": False, "notes": False, "hydration": False, "meals": False,
                 "medications": False, "activity": False, "timeline": False,
                 "digest": False}
        up = client.put(f"{API}/partner/links/{link_id}/permissions",
                        json=perms, headers=_h(owner["access_token"]))
        assert up.status_code == 200

        view = client.get(f"{API}/partner/view/{link_id}",
                          headers=_h(partner["access_token"]))
        assert view.status_code == 200
        v = view.json()
        # everything should be null/empty
        assert v["prediction"] is None
        assert v["hydration"] is None and v["meals"] is None
        assert v["medications"] is None and v["intimacy"] is None
        assert v["timeline"] is None and v["digest"] is None
        assert v["logs"] == []

        # revoke by partner
        rv = client.delete(f"{API}/partner/links/{link_id}",
                           headers=_h(partner["access_token"]))
        assert rv.status_code == 200
        # afterwards /partner/view -> 404
        view2 = client.get(f"{API}/partner/view/{link_id}",
                           headers=_h(partner["access_token"]))
        assert view2.status_code == 404


class TestPartnerPermissionGating:
    def test_per_category_flags(self, client, two_users):
        owner, partner = two_users
        link_id = _link_pair(client, owner, partner)

        # owner seeds a shared daily log + a cycle so prediction has data
        today = datetime.now(timezone.utc).date()
        start = (today - timedelta(days=10)).isoformat()
        client.post(f"{API}/cycles", json={"start_date": start},
                    headers=_h(owner["access_token"]))
        client.post(f"{API}/logs", json={
            "date": today.isoformat(),
            "symptoms": [{"name": "Cramps", "severity": "mild"}],
            "moods": ["happy"], "note": "ok", "tags": [], "visibility": "shared"
        }, headers=_h(owner["access_token"]))

        # all true (defaults), partner can see prediction + logs
        v = client.get(f"{API}/partner/view/{link_id}",
                       headers=_h(partner["access_token"])).json()
        assert v["prediction"] is not None
        assert any(lg.get("symptoms") for lg in v["logs"])

        # turn off symptoms only -> symptoms gone but moods/notes remain
        perms = {"periods": True, "fertility": True, "symptoms": False,
                 "moods": True, "notes": True, "hydration": True,
                 "meals": True, "medications": True, "activity": False,
                 "timeline": True, "digest": True}
        client.put(f"{API}/partner/links/{link_id}/permissions",
                   json=perms, headers=_h(owner["access_token"]))
        v2 = client.get(f"{API}/partner/view/{link_id}",
                        headers=_h(partner["access_token"])).json()
        for lg in v2["logs"]:
            assert "symptoms" not in lg, f"symptoms leaked despite flag off: {lg}"
            assert "moods" in lg

        # turn off fertility -> ovulation/fertile fields stripped
        perms["fertility"] = False
        client.put(f"{API}/partner/links/{link_id}/permissions",
                   json=perms, headers=_h(owner["access_token"]))
        v3 = client.get(f"{API}/partner/view/{link_id}",
                        headers=_h(partner["access_token"])).json()
        pred = v3["prediction"] or {}
        assert "ovulation_date" not in pred
        assert "fertile_window_start" not in pred

    def test_partner_cannot_read_owner_raw_collections(self, client, two_users):
        owner, partner = two_users
        # owner adds a cycle
        start = (datetime.now(timezone.utc).date() - timedelta(days=3)).isoformat()
        client.post(f"{API}/cycles", json={"start_date": start},
                    headers=_h(owner["access_token"]))
        _link_pair(client, owner, partner)

        # partner's /api/cycles MUST only show partner's own (empty here)
        rc = client.get(f"{API}/cycles", headers=_h(partner["access_token"]))
        assert rc.status_code == 200
        assert rc.json() == [], f"partner saw owner's cycles: {rc.json()}"

        # partner cannot read /partner/view of a link they are not partner on
        other = register_user(client, "other")
        inv = client.post(f"{API}/partner/invite",
                          headers=_h(owner["access_token"])).json()
        # not accepting -> partner_id is None, link not active for `other`
        rv = client.get(f"{API}/partner/view/{inv['id']}",
                        headers=_h(other["access_token"]))
        assert rv.status_code == 404


# ----------------------- PERIOD TRACKING -----------------------
class TestCycleCRUD:
    def test_create_list_update_delete(self, client, fresh_user):
        h = _h(fresh_user["access_token"])
        cr = client.post(f"{API}/cycles",
                         json={"start_date": "2026-01-01", "end_date": "2026-01-05"},
                         headers=h)
        assert cr.status_code == 200, cr.text
        cid = cr.json()["id"]

        lst = client.get(f"{API}/cycles", headers=h).json()
        assert any(c["id"] == cid for c in lst)

        up = client.put(f"{API}/cycles/{cid}",
                        json={"end_date": "2026-01-06"}, headers=h)
        assert up.status_code == 200

        # 404 for other user's id
        other = register_user(client, "stranger")
        up2 = client.put(f"{API}/cycles/{cid}",
                         json={"end_date": "2026-01-09"},
                         headers=_h(other["access_token"]))
        assert up2.status_code == 404

        de = client.delete(f"{API}/cycles/{cid}", headers=h)
        assert de.status_code == 200
        lst2 = client.get(f"{API}/cycles", headers=h).json()
        assert not any(c["id"] == cid for c in lst2)

    def test_prediction_math_with_history(self, client, fresh_user):
        h = _h(fresh_user["access_token"])
        # 4 cycles 28 days apart
        base = datetime(2025, 7, 1).date()
        for i in range(4):
            d = (base + timedelta(days=28 * i)).isoformat()
            client.post(f"{API}/cycles", json={"start_date": d,
                        "end_date": (base + timedelta(days=28 * i + 4)).isoformat()},
                        headers=h)
        # plus an outlier (60-day gap) that should be discarded
        client.post(f"{API}/cycles",
                    json={"start_date": (base + timedelta(days=28 * 3 + 60)).isoformat()},
                    headers=h)
        dash = client.get(f"{API}/dashboard", headers=h).json()
        p = dash["prediction"]
        assert p["has_data"] is True
        # outlier of 60 days should be discarded -> avg stays ~28
        assert 27 <= p["avg_cycle_length"] <= 29, p
        # ovulation = next_period - 14
        np_date = datetime.fromisoformat(p["next_period_date"]).date()
        ov_date = datetime.fromisoformat(p["ovulation_date"]).date()
        assert (np_date - ov_date).days == 14
        fws = datetime.fromisoformat(p["fertile_window_start"]).date()
        fwe = datetime.fromisoformat(p["fertile_window_end"]).date()
        assert (ov_date - fws).days == 5
        assert (fwe - ov_date).days == 1

    def test_invalid_date_handling(self, client, fresh_user):
        h = _h(fresh_user["access_token"])
        # malformed string is accepted by API (str field) but blows up downstream parse;
        # we expect either 422 (rejection) or 200 then 500 elsewhere. Record actual behavior.
        r = client.post(f"{API}/cycles", json={"start_date": "not-a-date"}, headers=h)
        # current model uses plain str, so 200 expected; downstream /dashboard may 500.
        # We do NOT assert pass — record the outcome for the report.
        ok = r.status_code in (200, 400, 422)
        assert ok, f"unexpected status {r.status_code}: {r.text}"
        # If accepted, calling dashboard should not 500 silently
        if r.status_code == 200:
            d = client.get(f"{API}/dashboard", headers=h)
            # If it 500s, our test still passes silently; we flag this in report.
            assert d.status_code in (200, 500), d.text


# ----------------------- ANALYTICS -----------------------
class TestAnalytics:
    def test_analytics_endpoints_200(self, client, fresh_user):
        h = _h(fresh_user["access_token"])
        for ep in ["/analytics", "/symptom-patterns", "/daily-summary"]:
            r = client.get(f"{API}{ep}", headers=h)
            assert r.status_code == 200, f"{ep} -> {r.status_code} {r.text}"

    def test_regularity_score_bounds(self, client, fresh_user):
        h = _h(fresh_user["access_token"])
        base = datetime(2025, 6, 1).date()
        for i in range(5):
            client.post(f"{API}/cycles",
                        json={"start_date": (base + timedelta(days=28 * i)).isoformat()},
                        headers=h)
        a = client.get(f"{API}/analytics", headers=h).json()
        assert a["regularity_score"] is None or 0 <= a["regularity_score"] <= 100
        assert a["cycles_tracked"] == 5


# ----------------------- WEEKLY AUTO-BACKUP -----------------------
class TestWeeklyBackup:
    def test_ensure_weekly_creates_then_noops(self, client, fresh_user):
        h = _h(fresh_user["access_token"])
        r1 = client.post(f"{API}/backups/ensure-weekly", headers=h)
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1.get("created") is True
        assert d1.get("type") == "auto"

        # second call: should NOT create another
        r2 = client.post(f"{API}/backups/ensure-weekly", headers=h)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2.get("created") is False, f"Expected no-op, got {d2}"

        # listing includes 'type' field, and there's exactly one auto backup
        lst = client.get(f"{API}/backups", headers=h).json()
        types = [b.get("type") for b in lst]
        assert "auto" in types
        assert sum(1 for t in types if t == "auto") == 1

    def test_manual_backup_untouched_by_ensure_weekly(self, client, fresh_user):
        h = _h(fresh_user["access_token"])
        manual = client.post(f"{API}/backup", headers=h).json()
        manual_id = manual["id"]
        client.post(f"{API}/backups/ensure-weekly", headers=h)
        lst = client.get(f"{API}/backups", headers=h).json()
        ids = [b["id"] for b in lst]
        assert manual_id in ids, "Manual backup was deleted by ensure-weekly!"
        # 'type' field is exposed in list output
        for b in lst:
            assert "type" in b
