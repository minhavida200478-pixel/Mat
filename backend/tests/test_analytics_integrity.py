"""
Data Integrity, Analytics Engine, API Contract & Partner-Privacy test suite.

Stack note: the original brief referenced NestJS/Prisma + Flutter. Our implemented
stack is FastAPI + MongoDB + Expo. These tests are the faithful adaptation:

  Task 1  -> Data persistence & boundary integrity   (TestBoundaryIntegrity)
  Task 2  -> Analytics engine math / extreme states   (TestAnalyticsEngine)
  Task 3  -> API contract + partner privacy wall       (TestChartContract / TestPartnerPrivacyWall)
  Task 4  -> Flutter widget/goldens                    (N/A on RN — see note at bottom)

Severity adaptation: our app uses a qualitative scale {mild, moderate, severe} instead
of a 0-5 numeric scale. The "exactly 0 / exactly 5 / out-of-bounds 6 / -1" boundary
intent is preserved by asserting the in-bounds set is accepted and every out-of-bounds
value (including numeric-strings, empty, wrong case) is rejected with HTTP 422.

All tests run against the live preview API via the shared fixtures in conftest.py.
Registration is funnelled through `register_user`, which transparently waits out the
production 10/min register rate-limit so the suite is deterministic without weakening
the live security control. Users that need data isolation (cold-start / single-entry /
outlier math, chart counts, partner links) get their own fresh accounts; the boundary
checks share one module-scoped account writing to distinct calendar dates.
"""
import re
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import requests

from tests.conftest import API, register_user

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ----------------------------------------------------------------------------
# Helpers + explicit mock-data fixtures (no abbreviation)
# ----------------------------------------------------------------------------
def _session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _log_payload(log_date, **overrides):
    """Canonical daily-log sync payload (the exact shape the mobile app sends)."""
    payload = {
        "date": log_date,
        "symptoms": [{"name": "Cramps", "severity": "moderate"}],
        "moods": ["Calm"],
        "note": "Felt fine today.",
        "tags": ["work"],
        "visibility": "private",
    }
    payload.update(overrides)
    return payload


def _make_cycles(client, headers, start_dates, period_len=None):
    """Create cycles for the given list of date objects (start dates)."""
    for s in start_dates:
        body = {"start_date": s.isoformat(), "end_date": None}
        if period_len is not None:
            body["end_date"] = (s + timedelta(days=period_len - 1)).isoformat()
        r = client.post(f"{API}/cycles", json=body, headers=headers, timeout=20)
        assert r.status_code == 200, r.text


@pytest.fixture(scope="module")
def shared_headers():
    """One reusable authenticated account for boundary checks (distinct dates)."""
    sess = _session()
    user = register_user(sess, "boundary")
    return _headers(user["access_token"])


# ============================================================================
# TASK 1 — DATA PERSISTENCE & BOUNDARY INTEGRITY
# ============================================================================
class TestBoundaryIntegrity:

    @pytest.mark.parametrize("severity", ["mild", "moderate", "severe"])
    def test_in_bounds_severity_saves(self, client, shared_headers, severity):
        """In-bounds severities (analogue of the valid 0..5 range) persist cleanly."""
        d = "2025-01-10"
        payload = _log_payload(d, symptoms=[{"name": "Headache", "severity": severity}])
        r = client.post(f"{API}/logs", json=payload, headers=shared_headers, timeout=20)
        assert r.status_code == 200, r.text
        g = client.get(f"{API}/logs/{d}", headers=shared_headers, timeout=20)
        assert g.json()["symptoms"][0]["severity"] == severity

    @pytest.mark.parametrize("bad", ["extreme", "6", "-1", "0", "5", "", "MILD", "none"])
    def test_out_of_bounds_severity_rejected(self, client, shared_headers, bad):
        """Out-of-bounds severities must raise strict 422 validation errors."""
        payload = _log_payload("2025-01-11",
                               symptoms=[{"name": "Acne", "severity": bad}])
        r = client.post(f"{API}/logs", json=payload, headers=shared_headers, timeout=20)
        assert r.status_code == 422, f"expected 422 for severity={bad!r}, got {r.status_code}"

    def test_timestamp_no_timezone_day_shift(self, client, shared_headers):
        """A log saved for a specific calendar day must NOT drift to an adjacent day.
        The server trusts the client's explicit YYYY-MM-DD (no implicit UTC
        re-derivation), and machine timestamps are stored in UTC ISO-8601."""
        target, before, after = "2025-02-15", "2025-02-14", "2025-02-16"
        r = client.post(f"{API}/logs", json=_log_payload(target),
                        headers=shared_headers, timeout=20)
        assert r.status_code == 200, r.text

        got = client.get(f"{API}/logs/{target}", headers=shared_headers, timeout=20).json()
        assert got["date"] == target, "calendar day shifted!"
        # Machine timestamps are persisted in UTC (BSON datetimes are naive-UTC on read).
        # Verify the creation timestamp aligns with the current UTC date — proving the
        # server is not writing local-timezone times that could roll the day over.
        utc_today = datetime.now(timezone.utc).date().isoformat()
        assert got["created_at"].startswith(utc_today), \
            f"created_at not a UTC timestamp: {got['created_at']}"

        for neighbour in (before, after):
            n = client.get(f"{API}/logs/{neighbour}", headers=shared_headers, timeout=20).json()
            assert n["symptoms"] == [] and n["moods"] == [], \
                f"data leaked into adjacent day {neighbour}"

    def test_idempotent_double_submission(self, client, shared_headers):
        """A duplicated sync payload (network stutter) must upsert the SAME record,
        never create a duplicate row for that (user, date)."""
        d = "2025-03-01"
        payload = _log_payload(d, moods=["Happy"])
        a = client.post(f"{API}/logs", json=payload, headers=shared_headers, timeout=20)
        b = client.post(f"{API}/logs", json=payload, headers=shared_headers, timeout=20)
        assert a.status_code == 200 and b.status_code == 200

        all_logs = client.get(f"{API}/logs", headers=shared_headers, timeout=20).json()
        matches = [x for x in all_logs if x["date"] == d]
        assert len(matches) == 1, f"duplicate records created: {len(matches)}"

    def test_resubmission_updates_existing_record(self, client, shared_headers):
        """Re-submitting the same date with changed values updates in place."""
        d = "2025-03-02"
        client.post(f"{API}/logs", json=_log_payload(d, moods=["Tired"]),
                    headers=shared_headers, timeout=20)
        client.post(f"{API}/logs", json=_log_payload(d, moods=["Energetic"], note="updated"),
                    headers=shared_headers, timeout=20)
        got = client.get(f"{API}/logs/{d}", headers=shared_headers, timeout=20).json()
        assert got["moods"] == ["Energetic"] and got["note"] == "updated"


# ============================================================================
# TASK 2 — ANALYTICS ENGINE & MATH (extreme data states)
# ============================================================================
class TestAnalyticsEngine:

    def test_cold_start_zero_data_safe_defaults(self, client):
        """Zero periods: no division-by-zero; safe nulls; dashboard still 200."""
        h = _headers(register_user(client, "cold")["access_token"])
        body = client.get(f"{API}/analytics", headers=h, timeout=20).json()
        assert body["avg_cycle_length"] is None
        assert body["avg_period_length"] is None
        assert body["regularity_score"] is None
        assert body["cycles_tracked"] == 0
        assert body["cycle_lengths"] == []
        assert body["cycle_history"] == []

        pred = client.get(f"{API}/dashboard", headers=h, timeout=20).json()["prediction"]
        assert pred["has_data"] is False
        assert pred["avg_cycle_length"] == 28   # safe statistical default
        assert pred["avg_period_length"] == 5

    def test_single_entry_cannot_compute_cycle_length(self, client):
        """One period: cycle length is mathematically undefined (need >=2 starts)."""
        h = _headers(register_user(client, "single")["access_token"])
        _make_cycles(client, h, [date.today() - timedelta(days=10)], period_len=5)
        body = client.get(f"{API}/analytics", headers=h, timeout=20).json()
        assert body["cycles_tracked"] == 1
        assert body["cycle_lengths"] == []
        assert body["cycle_history"] == []
        assert body["avg_cycle_length"] is None
        assert body["regularity_score"] is None

        pred = client.get(f"{API}/dashboard", headers=h, timeout=20).json()["prediction"]
        assert pred["has_data"] is True
        assert "cycle_day" in pred and "next_period_date" in pred

    def test_outlier_filtration(self, client):
        """Normal cycles (28, 30) mixed with anomalies (120-day missed-log gap and a
        3-day accidental log): outliers (<21 or >45 days) are filtered from the
        average per blueprint, while raw lengths remain exposed for charting."""
        h = _headers(register_user(client, "outlier")["access_token"])
        base = date.today() - timedelta(days=210)
        starts = [
            base,                          # anchor
            base + timedelta(days=28),     # length 28  (valid)
            base + timedelta(days=58),     # length 30  (valid)
            base + timedelta(days=178),    # length 120 (outlier - missed log)
            base + timedelta(days=181),    # length 3   (outlier - accidental log)
        ]
        _make_cycles(client, h, starts)

        body = client.get(f"{API}/analytics", headers=h, timeout=20).json()
        assert body["cycles_tracked"] == 5
        assert body["cycle_lengths"] == [28, 30, 120, 3]   # raw preserved for chart
        assert body["avg_cycle_length"] == 29.0            # mean(28, 30)
        assert body["regularity_score"] == 88              # 100 - 12*pstdev([28,30]=1)

        pred = client.get(f"{API}/dashboard", headers=h, timeout=20).json()["prediction"]
        assert pred["avg_cycle_length"] == 29


# ============================================================================
# TASK 3a — API CONTRACT / CHART SCHEMA COMPLIANCE
# ============================================================================
class TestChartContract:

    def test_chart_payloads_are_flat_and_chronological(self, client):
        """Analytics must serve graph-ready, flat structures so the frontend does
        no heavy reshaping or sorting."""
        h = _headers(register_user(client, "chart")["access_token"])
        base = date.today() - timedelta(days=120)
        _make_cycles(client, h, [base, base + timedelta(days=29), base + timedelta(days=57)])
        client.post(f"{API}/logs",
                    json=_log_payload("2025-04-01",
                                      symptoms=[{"name": "Cramps", "severity": "severe"}]),
                    headers=h, timeout=20)
        client.post(f"{API}/logs",
                    json=_log_payload("2025-04-02",
                                      symptoms=[{"name": "Cramps", "severity": "mild"}]),
                    headers=h, timeout=20)

        body = client.get(f"{API}/analytics", headers=h, timeout=20).json()

        sf = body["symptom_frequency"]
        assert isinstance(sf, list) and len(sf) >= 1
        for item in sf:
            assert set(item.keys()) == {"name", "count"}
            assert isinstance(item["name"], str) and isinstance(item["count"], int)
        counts = [i["count"] for i in sf]
        assert counts == sorted(counts, reverse=True)            # no frontend sort needed
        assert next(i["count"] for i in sf if i["name"] == "Cramps") == 2

        ch = body["cycle_history"]
        assert isinstance(ch, list) and len(ch) == 2
        for item in ch:
            assert set(item.keys()) == {"date", "length"}
            assert DATE_RE.match(item["date"])
            assert isinstance(item["length"], int)
        dates = [i["date"] for i in ch]
        assert dates == sorted(dates), "cycle_history must be chronological"


# ============================================================================
# TASK 3b — PARTNER PORTAL PRIVACY WALL
# ============================================================================
@pytest.fixture(scope="class")
def linked_pair():
    """Register owner + partner ONCE, seed owner data, and link them.
    Returns sessions, headers and the link id; tests set the flags they need."""
    owner_sess, partner_sess = _session(), _session()
    owner = register_user(owner_sess, "owner")
    partner = register_user(partner_sess, "partner")
    h_a, h_b = _headers(owner["access_token"]), _headers(partner["access_token"])

    today = date.today()
    _make_cycles(owner_sess, h_a,
                 [today - timedelta(days=56), today - timedelta(days=28)], period_len=5)
    owner_sess.post(f"{API}/logs",
                    json={"date": today.isoformat(),
                          "symptoms": [{"name": "Cramps", "severity": "moderate"}],
                          "moods": ["Happy"], "note": "secret journal entry",
                          "tags": ["mood"], "visibility": "shared"},
                    headers=h_a, timeout=20)
    owner_sess.post(f"{API}/logs",
                    json={"date": (today - timedelta(days=1)).isoformat(),
                          "symptoms": [{"name": "Nausea", "severity": "mild"}],
                          "moods": ["Anxious"], "note": "private only",
                          "tags": [], "visibility": "private"},
                    headers=h_a, timeout=20)

    inv = owner_sess.post(f"{API}/partner/invite", headers=h_a, timeout=20).json()
    link_id, token = inv["id"], inv["token"]
    acc = partner_sess.post(f"{API}/partner/accept", json={"token": token},
                            headers=h_b, timeout=20)
    assert acc.status_code == 200, acc.text
    return {"owner_sess": owner_sess, "partner_sess": partner_sess,
            "h_a": h_a, "h_b": h_b, "link_id": link_id}


class TestPartnerPrivacyWall:

    def _set_flags(self, ctx, **flags):
        base = {"periods": True, "fertility": True, "symptoms": True,
                "moods": True, "notes": True}
        base.update(flags)
        r = ctx["owner_sess"].put(f"{API}/partner/links/{ctx['link_id']}/permissions",
                                  json=base, headers=ctx["h_a"], timeout=20)
        assert r.status_code == 200, r.text

    def _view(self, ctx):
        return ctx["partner_sess"].get(f"{API}/partner/view/{ctx['link_id']}",
                                       headers=ctx["h_b"], timeout=20).json()

    def test_notes_on_then_off(self, linked_pair):
        """'Share Notes' false -> note & tags absent; moods/symptoms remain."""
        self._set_flags(linked_pair, notes=True)
        on = self._view(linked_pair)["logs"][0]
        assert on["note"] == "secret journal entry" and "tags" in on

        self._set_flags(linked_pair, notes=False)
        off = self._view(linked_pair)["logs"][0]
        assert "note" not in off, f"NOTE LEAKED: {off}"
        assert "tags" not in off, f"TAGS LEAKED: {off}"
        assert "symptoms" in off and "moods" in off

    def test_fertility_flag_strips_prediction_fields(self, linked_pair):
        self._set_flags(linked_pair, fertility=False)
        pred = self._view(linked_pair)["prediction"]
        assert "ovulation_date" not in pred
        assert "fertile_window_start" not in pred
        assert "next_period_date" in pred       # periods still shared

    def test_private_logs_never_shared_regardless_of_flags(self, linked_pair):
        """visibility=private logs must NEVER appear, even with all flags on."""
        self._set_flags(linked_pair)  # all True
        v = self._view(linked_pair)
        notes = [e.get("note") for e in v["logs"]]
        assert "private only" not in notes, "private log exposed to partner!"
        assert len(v["logs"]) == 1   # only the single shared log

    def test_stranger_cannot_view_link(self, client, linked_pair):
        """A user with no active link gets 404 — never another user's data."""
        stranger = _headers(register_user(client, "stranger")["access_token"])
        r = client.get(f"{API}/partner/view/{linked_pair['link_id']}",
                       headers=stranger, timeout=20)
        assert r.status_code == 404


# ============================================================================
# TASK 4 — Flutter widget / golden tests
# ============================================================================
# Not applicable: this product is an Expo React Native app, not Flutter, so
# `flutter_test` / `mocktail` / golden files do not exist here. The equivalent
# UI-state coverage (LoadingState / EmptyState / DataLoadedState, chart layout
# scalability, tap-to-tooltip) is exercised via the Playwright-driven
# `testing_agent` against the live app (boot loader -> empty dashboard with no
# crash on zero data -> data-loaded dashboard with cycle ring/predictions/quick-log,
# /log interactions, calendar grid, insights charts, partner flow). See the run
# report under /app/test_reports/ for recorded evidence.
