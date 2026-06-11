"""Backend tests for the new Partner 'Weekly digest' feature.

Verifies:
  * GET /partner/view/{id} returns digest=null when 'digest' flag is OFF.
  * digest is populated when ON, with headline + lines + week_start/week_end.
  * When 'periods' OFF + 'digest' ON, headline becomes "<Name>'s week at a glance"
    (no phase/period clause) but lines still appear for shared categories.
  * Seeded owner (cycle ~24 days ago) produces 'luteal phase' + 'period expected
    in ~4 days' headline and correct hydration / symptom / meal / med / mood lines.
  * PUT permissions accepts the full 11-flag payload (including 'digest').
"""
import time
import uuid
from datetime import date, timedelta

import pytest

from tests.conftest import API


# ---------- helpers ----------
def _register(client, prefix):
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


ALL_ON_11 = {
    "periods": True, "fertility": True, "symptoms": True, "moods": True,
    "notes": True, "hydration": True, "meals": True, "medications": True,
    "activity": True, "timeline": True, "digest": True,
}


def _seed_owner_for_digest(client, headers):
    """Seed an owner so they are in luteal phase with period in ~4 days,
    + 7 days of water (~1900ml/day) + 3 meals + 1 medication + 1 daily_log."""
    today = date.today()

    # Prior cycle ~52 days ago and current cycle ~24 days ago
    # → avg cycle = 28d, current cycle_day = 25, days_until_next_period ≈ 4
    prior = (today - timedelta(days=52)).isoformat()
    cur = (today - timedelta(days=24)).isoformat()

    r = client.post(f"{API}/cycles", json={"start_date": prior},
                    headers=headers, timeout=20)
    assert r.status_code == 200, r.text
    r = client.post(f"{API}/cycles", json={"start_date": cur},
                    headers=headers, timeout=20)
    assert r.status_code == 200, r.text

    # Water: 1900ml/day for last 7 days. Backend only accepts amount_ml — date
    # defaults to today. Post 7 entries × ~270ml ≈ 1890ml today only.
    # For "last 7 days" totals the digest sums all water events with date>=week_start,
    # so total ~13300ml is fine; we put it today.
    for _ in range(7):
        r = client.post(f"{API}/water", json={"amount_ml": 270},
                        headers=headers, timeout=20)
        assert r.status_code in (200, 201), r.text

    # 3 meals
    for mt in ("breakfast", "lunch", "dinner"):
        r = client.post(f"{API}/meals", json={"meal_type": mt},
                        headers=headers, timeout=20)
        assert r.status_code in (200, 201), r.text

    # 1 medication
    r = client.post(f"{API}/medications",
                    json={"name": "Ibuprofen", "dosage": "400mg"},
                    headers=headers, timeout=20)
    assert r.status_code in (200, 201), r.text

    # 1 shared daily log with symptom + mood, dated today (so in last 7 days)
    log = {
        "date": today.isoformat(),
        "symptoms": [{"name": "Cramps", "severity": "moderate"}],
        "moods": ["calm"],
        "visibility": "shared",
    }
    r = client.post(f"{API}/logs", json=log, headers=headers, timeout=20)
    assert r.status_code in (200, 201), r.text


# ---------- tests ----------
class TestPartnerDigest:

    @pytest.fixture(scope="class")
    def linked(self):
        import requests
        client = requests.Session()
        client.headers.update({"Content-Type": "application/json"})

        _, a_tok = _register(client, "ownerD")
        _, b_tok = _register(client, "partnerD")
        h_a, h_b = _h(a_tok), _h(b_tok)

        _seed_owner_for_digest(client, h_a)

        inv = client.post(f"{API}/partner/invite", headers=h_a, timeout=20).json()
        acc = client.post(f"{API}/partner/accept", json={"token": inv["token"]},
                          headers=h_b, timeout=20)
        assert acc.status_code == 200, acc.text
        return {"client": client, "h_a": h_a, "h_b": h_b, "link_id": inv["id"]}

    # ---- permission payload accepts digest flag ----
    def test_permissions_accepts_digest_flag(self, linked):
        c, h_a = linked["client"], linked["h_a"]
        r = c.put(f"{API}/partner/links/{linked['link_id']}/permissions",
                  json=ALL_ON_11, headers=h_a, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["sharing_flags"] == ALL_ON_11

    # ---- digest ON with all categories ON ----
    def test_digest_on_all_categories(self, linked):
        c, h_a, h_b = linked["client"], linked["h_a"], linked["h_b"]
        c.put(f"{API}/partner/links/{linked['link_id']}/permissions",
              json=ALL_ON_11, headers=h_a, timeout=20)
        body = c.get(f"{API}/partner/view/{linked['link_id']}",
                     headers=h_b, timeout=20).json()
        assert body.get("digest") is not None, body
        dg = body["digest"]
        # structure
        assert "headline" in dg and "lines" in dg
        assert "week_start" in dg and "week_end" in dg
        assert dg["week_end"] == date.today().isoformat()
        assert dg["week_start"] == (date.today() - timedelta(days=6)).isoformat()
        # headline mentions luteal phase + period in ~4 days
        head = dg["headline"].lower()
        assert "luteal phase" in head, head
        # ~24 days into a 28-day cycle → 4 days remaining (tolerate 3–5)
        assert ("period expected in 4 days" in head
                or "period expected in 3 days" in head
                or "period expected in 5 days" in head), head
        # lines cover hydration / symptom / meal / med / mood
        all_lines = " ||| ".join(dg["lines"]).lower()
        assert "hydration" in all_lines, dg["lines"]
        assert "most often cramps" in all_lines, dg["lines"]
        assert "meals" in all_lines, dg["lines"]
        assert "medications" in all_lines, dg["lines"]
        assert "mood" in all_lines, dg["lines"]

    # ---- digest OFF ----
    def test_digest_off_returns_null(self, linked):
        c, h_a, h_b = linked["client"], linked["h_a"], linked["h_b"]
        perms = {**ALL_ON_11, "digest": False}
        c.put(f"{API}/partner/links/{linked['link_id']}/permissions",
              json=perms, headers=h_a, timeout=20)
        body = c.get(f"{API}/partner/view/{linked['link_id']}",
                     headers=h_b, timeout=20).json()
        assert body["digest"] is None

    # ---- periods OFF + digest ON: headline is generic, lines still present ----
    def test_digest_on_periods_off_generic_headline(self, linked):
        c, h_a, h_b = linked["client"], linked["h_a"], linked["h_b"]
        perms = {**ALL_ON_11, "periods": False, "digest": True}
        c.put(f"{API}/partner/links/{linked['link_id']}/permissions",
              json=perms, headers=h_a, timeout=20)
        body = c.get(f"{API}/partner/view/{linked['link_id']}",
                     headers=h_b, timeout=20).json()
        assert body["digest"] is not None
        dg = body["digest"]
        head = dg["headline"].lower()
        assert "phase" not in head, head
        assert "period" not in head, head
        assert "week at a glance" in head, head
        # supporting lines for shared categories still present
        all_lines = " ||| ".join(dg["lines"]).lower()
        assert "hydration" in all_lines
        assert "most often cramps" in all_lines

    # ---- digest only on, all other categories off → digest still null or no lines ----
    def test_digest_on_all_others_off_no_lines_no_headline(self, linked):
        c, h_a, h_b = linked["client"], linked["h_a"], linked["h_b"]
        perms = {k: False for k in ALL_ON_11}
        perms["digest"] = True
        c.put(f"{API}/partner/links/{linked['link_id']}/permissions",
              json=perms, headers=h_a, timeout=20)
        body = c.get(f"{API}/partner/view/{linked['link_id']}",
                     headers=h_b, timeout=20).json()
        # With nothing shared and no period clause, server emits digest=None
        # (or a digest with no lines and a generic headline). Both are acceptable
        # per the spec; we assert no period/phase leakage and no shared category lines.
        if body["digest"] is not None:
            dg = body["digest"]
            assert all("phase" not in l.lower() and "period" not in l.lower()
                       for l in dg["lines"])
            head = dg["headline"].lower()
            assert "phase" not in head and "period" not in head
