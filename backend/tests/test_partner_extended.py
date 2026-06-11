"""Extended partner-sharing tests for the new categories (hydration, meals,
medications, activity, timeline) and per-category permission gating.

Verifies:
  * Invite/accept/links flow returns both 'sharing' and 'viewing' sides.
  * PUT /partner/links/{id}/permissions accepts the full 10-flag payload.
  * GET /partner/view/{id} respects each flag:
      - hydration/meals/medications/intimacy => null when flag false
      - prediction strips fertility keys when fertility=false
      - prediction strips period keys when periods=false
      - timeline omits sexual_activity entries when activity=false
      - timeline null when timeline=false
"""
import time
import uuid
from datetime import date

import pytest

from tests.conftest import API


# ---------- helpers ----------
def _register(client, prefix):
    """Register and return (email, access_token), handling rate-limit retry."""
    email = f"TEST_{prefix}_{uuid.uuid4().hex[:8]}@cycle.app"
    body = {"email": email, "password": "Password123",
            "full_name": prefix.title()}
    deadline = time.time() + 90
    while True:
        r = client.post(f"{API}/auth/register", json=body, timeout=20)
        if r.status_code == 429 and time.time() < deadline:
            time.sleep(6)
            continue
        assert r.status_code == 201, f"register {prefix}: {r.status_code} {r.text}"
        return email, r.json()["access_token"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


ALL_ON = {"periods": True, "fertility": True, "symptoms": True, "moods": True,
          "notes": True, "hydration": True, "meals": True, "medications": True,
          "activity": True, "timeline": True, "digest": True}


def _seed_owner(client, headers):
    """Seed owner with cycle + water + meal + medication + intimacy."""
    today = date.today().isoformat()
    # cycle (single → prediction populated)
    r = client.post(f"{API}/cycles", json={"start_date": today},
                    headers=headers, timeout=20)
    assert r.status_code == 200, r.text
    # water
    r = client.post(f"{API}/water", json={"amount_ml": 500},
                    headers=headers, timeout=20)
    assert r.status_code in (200, 201), r.text
    # meal
    r = client.post(f"{API}/meals", json={"meal_type": "breakfast"},
                    headers=headers, timeout=20)
    assert r.status_code in (200, 201), r.text
    # medication
    r = client.post(f"{API}/medications",
                    json={"name": "Ibuprofen", "dosage": "400mg"},
                    headers=headers, timeout=20)
    assert r.status_code in (200, 201), r.text
    # sexual activity (for intimacy + activity timeline tests)
    r = client.post(f"{API}/sexual-activity",
                    json={"protection_used": True, "partner_present": True},
                    headers=headers, timeout=20)
    assert r.status_code in (200, 201), r.text


# ---------- tests ----------
class TestPartnerExtended:

    @pytest.fixture(scope="class")
    def linked_pair(self):
        import requests
        client = requests.Session()
        client.headers.update({"Content-Type": "application/json"})

        _, a_tok = _register(client, "ownerX")
        _, b_tok = _register(client, "partnerX")
        h_a, h_b = _h(a_tok), _h(b_tok)

        _seed_owner(client, h_a)

        inv = client.post(f"{API}/partner/invite", headers=h_a, timeout=20)
        assert inv.status_code == 200, inv.text
        link_id = inv.json()["id"]
        token = inv.json()["token"]

        acc = client.post(f"{API}/partner/accept", json={"token": token},
                          headers=h_b, timeout=20)
        assert acc.status_code == 200, acc.text

        return {"client": client, "h_a": h_a, "h_b": h_b,
                "link_id": link_id, "token": token}

    # --- invite/accept/links flow ---
    def test_invite_token_uppercase_and_expiry(self, linked_pair):
        # token returned by invite is uppercased 8 chars
        c = linked_pair["client"]
        h_a = linked_pair["h_a"]
        inv = c.post(f"{API}/partner/invite", headers=h_a, timeout=20)
        assert inv.status_code == 200
        body = inv.json()
        assert body["token"] == body["token"].upper()
        assert len(body["token"]) == 8
        assert "expires_at" in body

    def test_links_lists_sharing_and_viewing(self, linked_pair):
        c, h_a, h_b = linked_pair["client"], linked_pair["h_a"], linked_pair["h_b"]
        # Owner sees 'sharing'
        r1 = c.get(f"{API}/partner/links", headers=h_a, timeout=20)
        assert r1.status_code == 200
        sharing = r1.json()["sharing"]
        ids = [s["id"] for s in sharing]
        assert linked_pair["link_id"] in ids
        active = next(s for s in sharing if s["id"] == linked_pair["link_id"])
        assert active["status"] == "active"
        assert active["partner_name"]  # partner identity exposed to owner

        # Partner sees 'viewing'
        r2 = c.get(f"{API}/partner/links", headers=h_b, timeout=20)
        assert r2.status_code == 200
        viewing = r2.json()["viewing"]
        assert any(v["id"] == linked_pair["link_id"] for v in viewing)

    # --- permissions update accepts full 10-flag payload ---
    def test_permissions_full_flag_payload(self, linked_pair):
        c, h_a = linked_pair["client"], linked_pair["h_a"]
        r = c.put(f"{API}/partner/links/{linked_pair['link_id']}/permissions",
                  json=ALL_ON, headers=h_a, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["sharing_flags"] == ALL_ON

    # --- all flags ON → everything present ---
    def test_view_all_on_returns_all_categories(self, linked_pair):
        c, h_a, h_b = linked_pair["client"], linked_pair["h_a"], linked_pair["h_b"]
        c.put(f"{API}/partner/links/{linked_pair['link_id']}/permissions",
              json=ALL_ON, headers=h_a, timeout=20)
        v = c.get(f"{API}/partner/view/{linked_pair['link_id']}",
                  headers=h_b, timeout=20)
        assert v.status_code == 200, v.text
        body = v.json()
        assert body["owner_name"]
        assert body["flags"] == ALL_ON
        # prediction populated
        assert body["prediction"] is not None
        for k in ("cycle_day", "next_period_date",
                  "ovulation_date", "fertile_window_start", "fertile_window_end"):
            assert k in body["prediction"], f"missing {k}"
        # health categories
        assert body["hydration"] is not None and body["hydration"]["total_ml"] >= 500
        assert body["meals"] is not None
        assert body["meals"]["completed_count"] >= 1
        assert body["medications"] is not None
        assert body["medications"]["count"] >= 1
        names = [m["name"] for m in body["medications"]["items"]]
        assert "Ibuprofen" in names
        assert body["intimacy"] is not None
        assert body["intimacy"]["count"] >= 1
        # timeline contains water + meal + medication + sexual_activity entries
        assert body["timeline"] is not None
        types = {t["event_type"] for t in body["timeline"]}
        assert {"water", "meal", "medication", "sexual_activity"}.issubset(types), types

    # --- per-category gating ---
    def test_view_hydration_off(self, linked_pair):
        c, h_a, h_b = linked_pair["client"], linked_pair["h_a"], linked_pair["h_b"]
        perms = {**ALL_ON, "hydration": False}
        c.put(f"{API}/partner/links/{linked_pair['link_id']}/permissions",
              json=perms, headers=h_a, timeout=20)
        body = c.get(f"{API}/partner/view/{linked_pair['link_id']}",
                     headers=h_b, timeout=20).json()
        assert body["hydration"] is None
        # timeline strips water entries
        assert body["timeline"] is not None
        assert all(t["event_type"] != "water" for t in body["timeline"])

    def test_view_meals_off(self, linked_pair):
        c, h_a, h_b = linked_pair["client"], linked_pair["h_a"], linked_pair["h_b"]
        perms = {**ALL_ON, "meals": False}
        c.put(f"{API}/partner/links/{linked_pair['link_id']}/permissions",
              json=perms, headers=h_a, timeout=20)
        body = c.get(f"{API}/partner/view/{linked_pair['link_id']}",
                     headers=h_b, timeout=20).json()
        assert body["meals"] is None
        assert all(t["event_type"] != "meal" for t in body["timeline"])

    def test_view_medications_off(self, linked_pair):
        c, h_a, h_b = linked_pair["client"], linked_pair["h_a"], linked_pair["h_b"]
        perms = {**ALL_ON, "medications": False}
        c.put(f"{API}/partner/links/{linked_pair['link_id']}/permissions",
              json=perms, headers=h_a, timeout=20)
        body = c.get(f"{API}/partner/view/{linked_pair['link_id']}",
                     headers=h_b, timeout=20).json()
        assert body["medications"] is None
        assert all(t["event_type"] != "medication" for t in body["timeline"])

    def test_view_activity_off_removes_intimacy(self, linked_pair):
        c, h_a, h_b = linked_pair["client"], linked_pair["h_a"], linked_pair["h_b"]
        perms = {**ALL_ON, "activity": False}
        c.put(f"{API}/partner/links/{linked_pair['link_id']}/permissions",
              json=perms, headers=h_a, timeout=20)
        body = c.get(f"{API}/partner/view/{linked_pair['link_id']}",
                     headers=h_b, timeout=20).json()
        assert body["intimacy"] is None
        # timeline must NOT contain sexual_activity
        assert all(t["event_type"] != "sexual_activity" for t in body["timeline"])

    def test_view_timeline_off_returns_null(self, linked_pair):
        c, h_a, h_b = linked_pair["client"], linked_pair["h_a"], linked_pair["h_b"]
        perms = {**ALL_ON, "timeline": False}
        c.put(f"{API}/partner/links/{linked_pair['link_id']}/permissions",
              json=perms, headers=h_a, timeout=20)
        body = c.get(f"{API}/partner/view/{linked_pair['link_id']}",
                     headers=h_b, timeout=20).json()
        assert body["timeline"] is None
        # but intimacy still present because activity is still on
        assert body["intimacy"] is not None

    def test_view_fertility_off_strips_fertility_keys(self, linked_pair):
        c, h_a, h_b = linked_pair["client"], linked_pair["h_a"], linked_pair["h_b"]
        perms = {**ALL_ON, "fertility": False}
        c.put(f"{API}/partner/links/{linked_pair['link_id']}/permissions",
              json=perms, headers=h_a, timeout=20)
        pred = c.get(f"{API}/partner/view/{linked_pair['link_id']}",
                     headers=h_b, timeout=20).json()["prediction"]
        assert pred is not None
        for k in ("ovulation_date", "fertile_window_start", "fertile_window_end"):
            assert k not in pred, f"{k} leaked when fertility=false"
        # periods still on
        assert "next_period_date" in pred
        assert "cycle_day" in pred

    def test_view_periods_off_strips_period_keys(self, linked_pair):
        c, h_a, h_b = linked_pair["client"], linked_pair["h_a"], linked_pair["h_b"]
        perms = {**ALL_ON, "periods": False}
        c.put(f"{API}/partner/links/{linked_pair['link_id']}/permissions",
              json=perms, headers=h_a, timeout=20)
        pred = c.get(f"{API}/partner/view/{linked_pair['link_id']}",
                     headers=h_b, timeout=20).json()["prediction"]
        assert pred is not None  # fertility still on so prediction object exists
        for k in ("next_period_date", "days_until_next_period",
                  "cycle_day", "last_period_start"):
            assert k not in pred, f"{k} leaked when periods=false"
        assert "ovulation_date" in pred  # fertility still on

    def test_view_periods_and_fertility_off_drops_prediction(self, linked_pair):
        c, h_a, h_b = linked_pair["client"], linked_pair["h_a"], linked_pair["h_b"]
        perms = {**ALL_ON, "periods": False, "fertility": False}
        c.put(f"{API}/partner/links/{linked_pair['link_id']}/permissions",
              json=perms, headers=h_a, timeout=20)
        body = c.get(f"{API}/partner/view/{linked_pair['link_id']}",
                     headers=h_b, timeout=20).json()
        assert body["prediction"] is None

    def test_partner_view_forbidden_to_non_partner(self, client):
        # Random third user trying to peek at the same link → 404
        _, c_tok = _register(client, "third")
        h_c = _h(c_tok)
        # First grab any active link's id from a fresh pair
        _, a_tok = _register(client, "ownerY")
        _, b_tok = _register(client, "partnerY")
        h_a, h_b = _h(a_tok), _h(b_tok)
        inv = client.post(f"{API}/partner/invite", headers=h_a, timeout=20).json()
        client.post(f"{API}/partner/accept", json={"token": inv["token"]},
                    headers=h_b, timeout=20)
        r = client.get(f"{API}/partner/view/{inv['id']}", headers=h_c, timeout=20)
        assert r.status_code == 404
