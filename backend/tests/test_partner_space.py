"""Tier 3 (shared space: notes/checkins/todos) + Tier 4 (cycle_awareness / symptom_trends)
tests for the partner dashboard. Uses live preview backend via EXPO_PUBLIC_BACKEND_URL.

Relies on /app/backend/tests/conftest.py for `client`, `api_url`, `register_user`.
"""
from __future__ import annotations
import time
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from .conftest import API, register_user


# -------------------- helpers --------------------

def _auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _today_iso() -> str:
    return date.today().isoformat()


def _create_pair_with_link(client, flags_override: dict | None = None,
                           seed_symptoms: bool = False, seed_cycle_today: bool = True):
    """Register owner+partner, create a sharing link with given flags, accept it.
    Returns (owner, partner, link_id)."""
    owner = register_user(client, "owner_ps")
    partner = register_user(client, "partner_ps")

    flags = {
        "periods": True, "fertility": True, "hydration": True, "meals": True,
        "medications": True, "symptoms": True, "moods": True, "notes": True,
        "activity": True, "timeline": True, "digest": True,
    }
    if flags_override is not None:
        flags.update(flags_override)

    # owner creates invite
    r = client.post(f"{API}/partner/invite", headers=_auth(owner["access_token"]))
    assert r.status_code in (200, 201), r.text
    link = r.json()
    token = link["token"]
    link_id = link["id"]

    # set the sharing flags via PUT permissions (owner)
    rp = client.put(f"{API}/partner/links/{link_id}/permissions", json=flags,
                    headers=_auth(owner["access_token"]))
    assert rp.status_code == 200, rp.text

    # partner accepts
    ra = client.post(f"{API}/partner/accept", json={"token": token},
                     headers=_auth(partner["access_token"]))
    assert ra.status_code in (200, 201), ra.text

    if seed_cycle_today:
        r = client.post(f"{API}/cycles",
                        json={"start_date": _today_iso(), "period_length": 5, "cycle_length": 28},
                        headers=_auth(owner["access_token"]))
        # Some implementations may already have a cycle; tolerate 200/201/400
        assert r.status_code in (200, 201, 400), r.text

    if seed_symptoms:
        # Seed 5 cycles, each with a Headache symptom one day before period start.
        for i in range(5, 0, -1):
            start = (date.today() - timedelta(days=28 * i)).isoformat()
            client.post(f"{API}/cycles",
                        json={"start_date": start, "period_length": 5, "cycle_length": 28},
                        headers=_auth(owner["access_token"]))
            d_before = (date.today() - timedelta(days=28 * i + 1)).isoformat()
            client.post(f"{API}/daily-logs",
                        json={"date": d_before, "symptoms": [{"name": "Headache"}],
                              "shared_with_partner": True},
                        headers=_auth(owner["access_token"]))

    return owner, partner, link_id


# -------------------- Tier 3: Partner Notes --------------------

class TestPartnerNotes:
    def test_owner_and_partner_can_create_and_list_with_mine_flag(self, client):
        owner, partner, link_id = _create_pair_with_link(client)
        # owner creates a note
        ro = client.post(f"{API}/partner/{link_id}/notes",
                         json={"text": "Hello from owner"}, headers=_auth(owner["access_token"]))
        assert ro.status_code == 201, ro.text
        note_o = ro.json()
        assert note_o["text"] == "Hello from owner"
        assert note_o["mine"] is True
        assert note_o.get("author_name")

        # partner creates a note
        rp = client.post(f"{API}/partner/{link_id}/notes",
                         json={"text": "Hi from partner"}, headers=_auth(partner["access_token"]))
        assert rp.status_code == 201, rp.text
        note_p = rp.json()
        assert note_p["mine"] is True

        # owner list: owner's note mine=True, partner's mine=False
        lst = client.get(f"{API}/partner/{link_id}/notes",
                         headers=_auth(owner["access_token"])).json()["notes"]
        ids = {n["id"]: n for n in lst}
        assert note_o["id"] in ids and ids[note_o["id"]]["mine"] is True
        assert note_p["id"] in ids and ids[note_p["id"]]["mine"] is False
        for n in lst:
            assert n.get("author_name")

        # partner list: flips mine
        lst_p = client.get(f"{API}/partner/{link_id}/notes",
                           headers=_auth(partner["access_token"])).json()["notes"]
        ids_p = {n["id"]: n for n in lst_p}
        assert ids_p[note_o["id"]]["mine"] is False
        assert ids_p[note_p["id"]]["mine"] is True

    def test_only_author_can_delete_note(self, client):
        owner, partner, link_id = _create_pair_with_link(client)
        ro = client.post(f"{API}/partner/{link_id}/notes",
                         json={"text": "owners private"}, headers=_auth(owner["access_token"]))
        note_id = ro.json()["id"]
        # partner tries to delete -> 404 (not author)
        rdel_p = client.delete(f"{API}/partner/{link_id}/notes/{note_id}",
                               headers=_auth(partner["access_token"]))
        assert rdel_p.status_code == 404
        # still in list
        lst = client.get(f"{API}/partner/{link_id}/notes",
                         headers=_auth(owner["access_token"])).json()["notes"]
        assert any(n["id"] == note_id for n in lst)
        # owner deletes -> 200
        rdel_o = client.delete(f"{API}/partner/{link_id}/notes/{note_id}",
                               headers=_auth(owner["access_token"]))
        assert rdel_o.status_code == 200
        lst2 = client.get(f"{API}/partner/{link_id}/notes",
                          headers=_auth(owner["access_token"])).json()["notes"]
        assert not any(n["id"] == note_id for n in lst2)

    def test_empty_text_rejected(self, client):
        owner, _partner, link_id = _create_pair_with_link(client)
        r = client.post(f"{API}/partner/{link_id}/notes", json={"text": "   "},
                        headers=_auth(owner["access_token"]))
        assert r.status_code == 400


# -------------------- Tier 3: Check-Ins --------------------

class TestPartnerCheckins:
    def test_create_lists_with_can_respond_flips(self, client):
        owner, partner, link_id = _create_pair_with_link(client)
        rc = client.post(f"{API}/partner/{link_id}/checkins",
                         json={"prompt": "How are you feeling?"},
                         headers=_auth(owner["access_token"]))
        assert rc.status_code == 201, rc.text
        ck = rc.json()
        assert ck["mine"] is True
        assert ck["can_respond"] is False  # creator cannot respond

        # partner sees can_respond=True
        lst_p = client.get(f"{API}/partner/{link_id}/checkins",
                           headers=_auth(partner["access_token"])).json()["checkins"]
        ck_p = next(c for c in lst_p if c["id"] == ck["id"])
        assert ck_p["mine"] is False
        assert ck_p["can_respond"] is True

        # partner responds
        rr = client.post(f"{API}/partner/{link_id}/checkins/{ck['id']}/respond",
                         json={"response": "Pretty good"},
                         headers=_auth(partner["access_token"]))
        assert rr.status_code == 200, rr.text
        out = rr.json()
        assert out["response"] == "Pretty good"
        assert out["can_respond"] is False

        # subsequent list: can_respond=False for both
        lst_p2 = client.get(f"{API}/partner/{link_id}/checkins",
                            headers=_auth(partner["access_token"])).json()["checkins"]
        assert next(c for c in lst_p2 if c["id"] == ck["id"])["can_respond"] is False
        lst_o = client.get(f"{API}/partner/{link_id}/checkins",
                           headers=_auth(owner["access_token"])).json()["checkins"]
        assert next(c for c in lst_o if c["id"] == ck["id"])["response"] == "Pretty good"

    def test_checkins_newest_first(self, client):
        owner, _partner, link_id = _create_pair_with_link(client)
        ids = []
        for i in range(3):
            r = client.post(f"{API}/partner/{link_id}/checkins",
                            json={"prompt": f"Q{i}"}, headers=_auth(owner["access_token"]))
            ids.append(r.json()["id"])
            time.sleep(0.05)
        lst = client.get(f"{API}/partner/{link_id}/checkins",
                         headers=_auth(owner["access_token"])).json()["checkins"]
        # newest (last created) is first
        assert lst[0]["id"] == ids[-1]


# -------------------- Tier 3: Shared To-Do --------------------

class TestPartnerTodos:
    def test_crud_and_ordering(self, client):
        owner, partner, link_id = _create_pair_with_link(client)
        # owner adds 2
        a = client.post(f"{API}/partner/{link_id}/todos", json={"text": "A"},
                       headers=_auth(owner["access_token"])).json()
        b = client.post(f"{API}/partner/{link_id}/todos", json={"text": "B"},
                       headers=_auth(owner["access_token"])).json()
        # partner adds 1
        c = client.post(f"{API}/partner/{link_id}/todos", json={"text": "C"},
                       headers=_auth(partner["access_token"])).json()

        assert all(not t["done"] for t in (a, b, c))
        assert a.get("created_by_name") and c.get("created_by_name")

        # partner toggles A done
        rt = client.put(f"{API}/partner/{link_id}/todos/{a['id']}", json={"done": True},
                        headers=_auth(partner["access_token"]))
        assert rt.status_code == 200 and rt.json()["done"] is True

        # list: incomplete first, newest first within group
        lst = client.get(f"{API}/partner/{link_id}/todos",
                         headers=_auth(owner["access_token"])).json()["todos"]
        ids_in_order = [t["id"] for t in lst]
        # First two should be incomplete (B and C in newest-first order: c then b)
        assert ids_in_order[0] == c["id"]
        assert ids_in_order[1] == b["id"]
        # done one (A) must be after the incomplete ones
        assert ids_in_order.index(a["id"]) > ids_in_order.index(b["id"])

        # toggle back to undone
        rt2 = client.put(f"{API}/partner/{link_id}/todos/{a['id']}", json={"done": False},
                        headers=_auth(owner["access_token"]))
        assert rt2.status_code == 200 and rt2.json()["done"] is False

        # delete by partner (either member can delete)
        rd = client.delete(f"{API}/partner/{link_id}/todos/{b['id']}",
                           headers=_auth(partner["access_token"]))
        assert rd.status_code == 200
        lst2 = client.get(f"{API}/partner/{link_id}/todos",
                          headers=_auth(owner["access_token"])).json()["todos"]
        assert not any(t["id"] == b["id"] for t in lst2)


# -------------------- Membership guard --------------------

class TestMembershipGuard:
    def test_non_member_gets_404_on_all_shared_endpoints(self, client):
        owner, _partner, link_id = _create_pair_with_link(client)
        outsider = register_user(client, "outsider")
        h = _auth(outsider["access_token"])

        endpoints = [
            ("GET", f"/partner/{link_id}/notes", None),
            ("POST", f"/partner/{link_id}/notes", {"text": "hack"}),
            ("DELETE", f"/partner/{link_id}/notes/{uuid.uuid4()}", None),
            ("GET", f"/partner/{link_id}/checkins", None),
            ("POST", f"/partner/{link_id}/checkins", {"prompt": "hack"}),
            ("POST", f"/partner/{link_id}/checkins/{uuid.uuid4()}/respond", {"response": "x"}),
            ("GET", f"/partner/{link_id}/todos", None),
            ("POST", f"/partner/{link_id}/todos", {"text": "x"}),
            ("PUT", f"/partner/{link_id}/todos/{uuid.uuid4()}", {"done": True}),
            ("DELETE", f"/partner/{link_id}/todos/{uuid.uuid4()}", None),
        ]
        for method, path, body in endpoints:
            url = f"{API}{path}"
            if method == "GET":
                r = client.get(url, headers=h)
            elif method == "POST":
                r = client.post(url, json=body, headers=h)
            elif method == "PUT":
                r = client.put(url, json=body, headers=h)
            else:
                r = client.delete(url, headers=h)
            assert r.status_code == 404, f"{method} {path} -> {r.status_code} ({r.text[:120]})"


# -------------------- Tier 4: cycle_awareness --------------------

class TestCycleAwareness:
    def test_cycle_awareness_present_when_periods_or_fertility_shared(self, client):
        owner, partner, link_id = _create_pair_with_link(client)  # all flags on
        r = client.get(f"{API}/partner/view/{link_id}", headers=_auth(partner["access_token"]))
        assert r.status_code == 200
        ca = r.json().get("cycle_awareness")
        assert ca is not None
        for k in ("cycle_day", "phase", "phase_title", "description", "period_window"):
            assert k in ca
        assert isinstance(ca["cycle_day"], int) and ca["cycle_day"] >= 1
        assert ca["phase"] in {"menstrual", "follicular", "ovulation", "luteal"}
        assert ca["phase_title"]
        assert ca["description"]
        # periods is shared -> period_window must be a string
        assert isinstance(ca["period_window"], str) and ca["period_window"]

    def test_period_window_null_when_periods_flag_off(self, client):
        owner, partner, link_id = _create_pair_with_link(
            client, flags_override={"periods": False, "fertility": True})
        r = client.get(f"{API}/partner/view/{link_id}", headers=_auth(partner["access_token"]))
        assert r.status_code == 200
        ca = r.json().get("cycle_awareness")
        assert ca is not None, "cycle_awareness should still exist when fertility is shared"
        assert ca.get("period_window") is None

    def test_cycle_awareness_null_when_periods_and_fertility_off(self, client):
        owner, partner, link_id = _create_pair_with_link(
            client, flags_override={"periods": False, "fertility": False})
        r = client.get(f"{API}/partner/view/{link_id}", headers=_auth(partner["access_token"]))
        assert r.status_code == 200
        assert r.json().get("cycle_awareness") is None


# -------------------- Tier 4: symptom_trends --------------------

class TestSymptomTrends:
    def test_trends_null_when_symptoms_flag_off(self, client):
        # Use the seeded link with rich symptom history, but create a fresh pair w/ symptoms off
        owner, partner, link_id = _create_pair_with_link(
            client, flags_override={"symptoms": False}, seed_symptoms=True)
        r = client.get(f"{API}/partner/view/{link_id}", headers=_auth(partner["access_token"]))
        assert r.status_code == 200
        assert r.json().get("symptom_trends") is None

    def test_trends_populated_for_seeded_owner(self, client):
        """Use the pre-seeded link in the environment that already has rich symptom data."""
        # Login the seeded partner
        r = client.post(f"{API}/auth/login",
                        json={"email": "prt_f2257@cycle.app", "password": "DemoPass123!"})
        if r.status_code != 200:
            pytest.skip(f"Seeded partner unavailable: {r.status_code}")
        tok = r.json()["access_token"]
        link_id = "f2ea1ed7-4c3f-4f24-9e24-9ed1919ce8d6"
        rv = client.get(f"{API}/partner/view/{link_id}", headers=_auth(tok))
        assert rv.status_code == 200, rv.text
        st = rv.json().get("symptom_trends")
        assert st is not None, "Expected symptom_trends to be populated for seeded owner"
        assert isinstance(st.get("lines"), list) and st["lines"]
        assert isinstance(st.get("cycles_tracked"), int) and st["cycles_tracked"] >= 1
        # Educational format check
        joined = " ".join(st["lines"]).lower()
        assert ("%" in " ".join(st["lines"])) and (
            "occurs" in joined or "tends to appear before the period" in joined
        )


# -------------------- Regression: existing partner-view fields ---------

class TestPartnerViewRegression:
    def test_seeded_partner_view_has_all_expected_fields(self, client):
        r = client.post(f"{API}/auth/login",
                        json={"email": "prt_f2257@cycle.app", "password": "DemoPass123!"})
        if r.status_code != 200:
            pytest.skip("Seeded partner unavailable")
        tok = r.json()["access_token"]
        link_id = "f2ea1ed7-4c3f-4f24-9e24-9ed1919ce8d6"
        rv = client.get(f"{API}/partner/view/{link_id}", headers=_auth(tok))
        assert rv.status_code == 200
        d = rv.json()
        for key in ("prediction", "calendar", "care_suggestions", "timeline",
                    "hydration", "meals", "medications", "digest", "last_updated",
                    "cycle_awareness", "symptom_trends"):
            assert key in d, f"missing key: {key}"
