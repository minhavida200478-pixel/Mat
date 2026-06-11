"""Tier 5 Partner Dashboard tests (iteration 15).

Coverage:
  * Prediction confidence (0-100, capped at 95) appears in
    GET /api/partner/view when periods OR fertility is shared.
  * Weekly summary keys are permission-gated:
        cycle_day (periods), water_avg_pct (hydration),
        symptoms_logged (symptoms), medication_entries (medications),
        mood_trend (moods)
  * Support history auto-logs supportive actions:
        notes ('Supportive note sent'),
        check-ins ('Check-in sent', 'Check-in completed'),
        shared to-dos ('Added a shared to-do'),
        explicit POST /support
    GET returns newest-first with actor_name + 'mine'.
  * Membership guard: stranger -> 404 on every support/alerts/emergency endpoint.
  * Emergency contact mode (owner-controlled):
        PUT /partner/links/{link_id}/emergency  (owner only; else 404)
        POST /partner/{link_id}/alerts          (owner only; 403 for partner;
                                                 400 when emergency disabled)
        GET  /partner/{link_id}/alerts          lists newest-first
        GET  /partner/view exposes emergency_contact + alerts[] only when on.
"""
import time
import uuid
from datetime import date, timedelta

import pytest

from tests.conftest import API


# ------------ helpers ------------
def _register(client, prefix):
    email = f"TEST_{prefix}_{uuid.uuid4().hex[:8]}@cycle.app"
    body = {"email": email, "password": "Password123",
            "full_name": prefix.title()}
    deadline = time.time() + 120
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


def _seed_owner(client, h):
    """Six regular 28-day cycles -> high prediction confidence; weekly hydration,
    symptoms, medication, mood activity so weekly_summary is populated."""
    today = date.today()
    # 6 cycles ending today (today = day 1 of new cycle for cycle_day=1)
    for i in range(6, 0, -1):
        start = (today - timedelta(days=28 * i)).isoformat()
        end = (today - timedelta(days=28 * i - 4)).isoformat()
        r = client.post(f"{API}/cycles", json={"start_date": start, "end_date": end},
                        headers=h, timeout=20)
        assert r.status_code == 200, r.text
    # current cycle starts today
    r = client.post(f"{API}/cycles", json={"start_date": today.isoformat()},
                    headers=h, timeout=20)
    assert r.status_code == 200, r.text
    # last 7 days of water + log entries (symptoms + moods) + meds
    for d in range(7):
        day = (today - timedelta(days=d)).isoformat()
        client.post(f"{API}/water", json={"amount_ml": 500, "date": day},
                    headers=h, timeout=20)
        client.post(f"{API}/medications",
                    json={"name": "VitaminD", "dosage": "1000IU", "date": day},
                    headers=h, timeout=20)
        client.post(f"{API}/logs", json={
            "date": day,
            "symptoms": [{"name": "Cramps", "severity": "moderate"}],
            "moods": ["happy"],
            "note": "Daily log",
            "visibility": "shared",
        }, headers=h, timeout=20)


# ------------ fixtures ------------
@pytest.fixture(scope="module")
def linked():
    import requests
    client = requests.Session()
    client.headers.update({"Content-Type": "application/json"})

    a_email, a_tok = _register(client, "ownerT5")
    b_email, b_tok = _register(client, "partnerT5")
    c_email, c_tok = _register(client, "outsiderT5")
    h_a, h_b, h_c = _h(a_tok), _h(b_tok), _h(c_tok)

    _seed_owner(client, h_a)

    inv = client.post(f"{API}/partner/invite", headers=h_a, timeout=20)
    assert inv.status_code == 200, inv.text
    link_id = inv.json()["id"]
    token = inv.json()["token"]
    acc = client.post(f"{API}/partner/accept", json={"token": token},
                      headers=h_b, timeout=20)
    assert acc.status_code == 200, acc.text

    # All flags on by default
    client.put(f"{API}/partner/links/{link_id}/permissions",
               json=ALL_ON, headers=h_a, timeout=20)

    return {"client": client, "h_a": h_a, "h_b": h_b, "h_c": h_c,
            "link_id": link_id, "a_email": a_email, "b_email": b_email}


def _view(linked, perms=None, headers=None):
    if perms is not None:
        linked["client"].put(f"{API}/partner/links/{linked['link_id']}/permissions",
                             json=perms, headers=linked["h_a"], timeout=20)
    r = linked["client"].get(f"{API}/partner/view/{linked['link_id']}",
                             headers=headers or linked["h_b"], timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


# ============== Prediction Confidence ==============
class TestPredictionConfidence:
    def test_confidence_present_and_capped(self, linked):
        body = _view(linked)
        pred = body["prediction"]
        assert pred is not None
        assert "confidence" in pred
        c = pred["confidence"]
        assert isinstance(c, int)
        assert 0 <= c <= 95, f"confidence must be <= 95, got {c}"
        # With 6+ regular cycles, confidence should be relatively high
        assert c >= 60, f"confidence too low for regular cycles: {c}"

    def test_confidence_absent_when_periods_and_fertility_off(self, linked):
        body = _view(linked, {**ALL_ON, "periods": False, "fertility": False})
        assert body["prediction"] is None

    def test_confidence_present_when_only_fertility_on(self, linked):
        body = _view(linked, {**ALL_ON, "periods": False})
        pred = body["prediction"]
        assert pred is not None
        # confidence stays as it's a meta/quality field
        assert pred.get("confidence") is not None
        assert pred["confidence"] <= 95


# ============== Weekly Summary (Tier 5) ==============
class TestWeeklySummary:
    def test_weekly_summary_all_keys_present_when_all_on(self, linked):
        body = _view(linked, ALL_ON)
        ws = body["weekly_summary"]
        assert ws is not None, "weekly_summary should be populated with all flags on"
        # expected keys
        assert "cycle_day" in ws
        assert "water_avg_pct" in ws
        assert "symptoms_logged" in ws
        assert "medication_entries" in ws
        assert "mood_trend" in ws
        # value sanity
        assert isinstance(ws["cycle_day"], int) and ws["cycle_day"] >= 1
        assert 0 <= ws["water_avg_pct"] <= 100
        assert ws["symptoms_logged"] >= 1
        assert ws["medication_entries"] >= 1
        assert ws["mood_trend"]  # non-empty string

    def test_periods_off_strips_cycle_day(self, linked):
        body = _view(linked, {**ALL_ON, "periods": False})
        ws = body["weekly_summary"] or {}
        assert "cycle_day" not in ws

    def test_hydration_off_strips_water(self, linked):
        body = _view(linked, {**ALL_ON, "hydration": False})
        ws = body["weekly_summary"] or {}
        assert "water_avg_pct" not in ws

    def test_symptoms_off_strips_symptoms_logged(self, linked):
        body = _view(linked, {**ALL_ON, "symptoms": False})
        ws = body["weekly_summary"] or {}
        assert "symptoms_logged" not in ws

    def test_medications_off_strips_medication_entries(self, linked):
        body = _view(linked, {**ALL_ON, "medications": False})
        ws = body["weekly_summary"] or {}
        assert "medication_entries" not in ws

    def test_moods_off_strips_mood_trend(self, linked):
        body = _view(linked, {**ALL_ON, "moods": False})
        ws = body["weekly_summary"] or {}
        assert "mood_trend" not in ws


# ============== Support History (Tier 5) ==============
class TestSupportHistory:
    def test_note_autologs_support(self, linked):
        c, h_b, lid = linked["client"], linked["h_b"], linked["link_id"]
        r = c.post(f"{API}/partner/{lid}/notes",
                   json={"text": "TEST_support_note"}, headers=h_b, timeout=20)
        assert r.status_code == 201, r.text
        sup = c.get(f"{API}/partner/{lid}/support", headers=h_b, timeout=20).json()
        labels = [s["label"] for s in sup["support"]]
        assert "Supportive note sent" in labels
        # newest-first + mine=True for the actor
        latest = sup["support"][0]
        assert latest["label"] == "Supportive note sent"
        assert latest["mine"] is True
        assert latest["actor_name"]

    def test_checkin_send_and_complete_autologs(self, linked):
        c, h_a, h_b, lid = linked["client"], linked["h_a"], linked["h_b"], linked["link_id"]
        r = c.post(f"{API}/partner/{lid}/checkins",
                   json={"prompt": "TEST_How are you?"}, headers=h_b, timeout=20)
        assert r.status_code == 201, r.text
        cid = r.json()["id"]
        # owner responds
        r2 = c.post(f"{API}/partner/{lid}/checkins/{cid}/respond",
                    json={"response": "Good"}, headers=h_a, timeout=20)
        assert r2.status_code == 200, r2.text
        sup = c.get(f"{API}/partner/{lid}/support", headers=h_a, timeout=20).json()["support"]
        labels = [s["label"] for s in sup]
        assert "Check-in sent" in labels
        assert "Check-in completed" in labels

    def test_todo_autologs_support(self, linked):
        c, h_b, lid = linked["client"], linked["h_b"], linked["link_id"]
        r = c.post(f"{API}/partner/{lid}/todos",
                   json={"text": "TEST_todo_support"}, headers=h_b, timeout=20)
        assert r.status_code == 201, r.text
        sup = c.get(f"{API}/partner/{lid}/support", headers=h_b, timeout=20).json()["support"]
        labels = [s["label"] for s in sup]
        assert "Added a shared to-do" in labels

    def test_explicit_support_post(self, linked):
        c, h_b, lid = linked["client"], linked["h_b"], linked["link_id"]
        r = c.post(f"{API}/partner/{lid}/support",
                   json={"kind": "reminder", "label": "TEST_Custom Support"},
                   headers=h_b, timeout=20)
        assert r.status_code == 201, r.text
        sup = c.get(f"{API}/partner/{lid}/support", headers=h_b, timeout=20).json()["support"]
        labels = [s["label"] for s in sup]
        assert "TEST_Custom Support" in labels

    def test_support_membership_guard(self, linked):
        c, h_c, lid = linked["client"], linked["h_c"], linked["link_id"]
        r = c.get(f"{API}/partner/{lid}/support", headers=h_c, timeout=20)
        assert r.status_code == 404
        r = c.post(f"{API}/partner/{lid}/support",
                   json={"kind": "x", "label": "y"}, headers=h_c, timeout=20)
        assert r.status_code == 404


# ============== Emergency Contact Mode (Tier 5) ==============
class TestEmergencyContactMode:
    def test_only_owner_can_toggle_emergency(self, linked):
        c, h_a, h_b, h_c, lid = (linked["client"], linked["h_a"], linked["h_b"],
                                 linked["h_c"], linked["link_id"])
        # partner -> 404
        r = c.put(f"{API}/partner/links/{lid}/emergency",
                  json={"enabled": True}, headers=h_b, timeout=20)
        assert r.status_code == 404
        # stranger -> 404
        r = c.put(f"{API}/partner/links/{lid}/emergency",
                  json={"enabled": True}, headers=h_c, timeout=20)
        assert r.status_code == 404
        # owner -> 200
        r = c.put(f"{API}/partner/links/{lid}/emergency",
                  json={"enabled": True}, headers=h_a, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["emergency_contact"] is True

    def test_partner_view_exposes_emergency_flag_and_alerts(self, linked):
        body = _view(linked)
        assert body["emergency_contact"] is True
        # alerts may be empty at this point but key must exist
        assert "alerts" in body

    def test_partner_cannot_send_alert_403(self, linked):
        c, h_b, lid = linked["client"], linked["h_b"], linked["link_id"]
        r = c.post(f"{API}/partner/{lid}/alerts",
                   json={"message": "TEST_alert_from_partner"},
                   headers=h_b, timeout=20)
        assert r.status_code == 403

    def test_stranger_cannot_send_alert_404(self, linked):
        c, h_c, lid = linked["client"], linked["h_c"], linked["link_id"]
        r = c.post(f"{API}/partner/{lid}/alerts",
                   json={"message": "TEST_alert_from_stranger"},
                   headers=h_c, timeout=20)
        assert r.status_code == 404

    def test_owner_can_send_alert_and_view_lists_it(self, linked):
        c, h_a, h_b, lid = linked["client"], linked["h_a"], linked["h_b"], linked["link_id"]
        r = c.post(f"{API}/partner/{lid}/alerts",
                   json={"message": "TEST_alert_health_concern"},
                   headers=h_a, timeout=20)
        assert r.status_code == 201, r.text
        alert_id = r.json()["id"]
        # GET alerts as partner (member)
        r2 = c.get(f"{API}/partner/{lid}/alerts", headers=h_b, timeout=20)
        assert r2.status_code == 200, r2.text
        ids = [a["id"] for a in r2.json()["alerts"]]
        assert alert_id in ids
        # /view shows alerts when emergency on
        body = _view(linked)
        view_ids = [a["id"] for a in body.get("alerts", [])]
        assert alert_id in view_ids

    def test_alert_blocked_when_emergency_disabled_400(self, linked):
        c, h_a, lid = linked["client"], linked["h_a"], linked["link_id"]
        # disable
        r = c.put(f"{API}/partner/links/{lid}/emergency",
                  json={"enabled": False}, headers=h_a, timeout=20)
        assert r.status_code == 200
        r = c.post(f"{API}/partner/{lid}/alerts",
                   json={"message": "TEST_disabled"}, headers=h_a, timeout=20)
        assert r.status_code == 400
        # partner-view: alerts not present when emergency off
        body = _view(linked)
        assert body["emergency_contact"] is False
        # spec: only when enabled does alerts surface; key may be [] default
        assert body.get("alerts", []) == []
        # re-enable for cleanup convenience
        c.put(f"{API}/partner/links/{lid}/emergency",
              json={"enabled": True}, headers=h_a, timeout=20)

    def test_alerts_membership_guard(self, linked):
        c, h_c, lid = linked["client"], linked["h_c"], linked["link_id"]
        r = c.get(f"{API}/partner/{lid}/alerts", headers=h_c, timeout=20)
        assert r.status_code == 404


# ============== Regression: existing partner features still work ==============
class TestRegression:
    def test_overview_calendar_timeline_care_present(self, linked):
        body = _view(linked, ALL_ON)
        assert body["prediction"] is not None
        assert body["calendar"] is not None
        assert body["timeline"] is not None
        assert isinstance(body["care_suggestions"], list)
        assert body["last_updated"]
        assert body["hydration"] is not None
        assert body["medications"] is not None
        assert body["cycle_awareness"] is not None
        # symptom_trends may be None if cycles not yet completed; allow.

    def test_digest_present(self, linked):
        body = _view(linked, ALL_ON)
        assert body["digest"] is not None
