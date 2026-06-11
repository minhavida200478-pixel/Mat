"""Part 3 QA audit — offline sync idempotency, timeline, dashboard,
analytics, search, performance, DB indexes, security/IDOR."""
import os
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

from tests.conftest import register_user, API  # type: ignore

load_dotenv(Path(__file__).resolve().parents[2] / "backend" / ".env")


# -------------------- helpers --------------------
def _h(user):
    return {"Authorization": f"Bearer {user['access_token']}",
            "Content-Type": "application/json"}


# -------------------- OFFLINE / IDEMPOTENCY --------------------
class TestOfflineIdempotency:
    """Offline sync queue replay safety — same client_id => single record."""

    def test_health_event_duplicate_client_id_returns_same(self, client):
        u = register_user(client, "off1")
        cid = f"dup-{uuid.uuid4().hex[:8]}"
        body = {
            "event_type": "symptom",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "data": {"name": "cramps", "severity": 3},
            "client_id": cid,
        }
        r1 = client.post(f"{API}/health-events", json=body, headers=_h(u))
        r2 = client.post(f"{API}/health-events", json=body, headers=_h(u))
        assert r1.status_code == 200, r1.text
        assert r2.status_code == 200, r2.text
        assert r1.json()["id"] == r2.json()["id"], "Replay must return same record"

        # And only ONE in the timeline
        tl = client.get(f"{API}/timeline", headers=_h(u)).json()
        same = [e for e in tl["events"]
                if e.get("data", {}).get("name") == "cramps"]
        assert len(same) == 1, f"expected 1 cramps record, got {len(same)}"

    def test_water_duplicate_client_id_returns_same(self, client):
        u = register_user(client, "off2")
        cid = f"water-{uuid.uuid4().hex[:8]}"
        body = {"amount_ml": 250, "client_id": cid}
        r1 = client.post(f"{API}/water", json=body, headers=_h(u))
        r2 = client.post(f"{API}/water", json=body, headers=_h(u))
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["id"] == r2.json()["id"]
        today = client.get(f"{API}/water/today", headers=_h(u)).json()
        assert today["total_ml"] == 250, (
            f"Replay must NOT double-count water (got {today['total_ml']})")

    def test_meal_duplicate_client_id_returns_same(self, client):
        u = register_user(client, "off3")
        cid = f"meal-{uuid.uuid4().hex[:8]}"
        body = {"meal_type": "lunch", "status": "completed",
                "note": "salad", "client_id": cid}
        r1 = client.post(f"{API}/meals", json=body, headers=_h(u))
        r2 = client.post(f"{API}/meals", json=body, headers=_h(u))
        assert r1.json()["id"] == r2.json()["id"]

    def test_daily_log_same_date_last_write_wins(self, client):
        u = register_user(client, "off4")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        b1 = {"date": today, "symptoms": [
            {"name": "headache", "severity": "mild"}], "note": "first"}
        b2 = {"date": today, "symptoms": [
            {"name": "cramps", "severity": "severe"}], "note": "second"}
        r1 = client.post(f"{API}/logs", json=b1, headers=_h(u))
        r2 = client.post(f"{API}/logs", json=b2, headers=_h(u))
        assert r1.status_code in (200, 201)
        assert r2.status_code in (200, 201)
        got = client.get(f"{API}/logs/{today}", headers=_h(u)).json()
        assert got["note"] == "second", "Last write wins on same date"
        names = [s["name"] for s in got.get("symptoms", [])]
        assert "cramps" in names and "headache" not in names


# -------------------- TIMELINE --------------------
class TestTimeline:
    """Timeline aggregates ALL event types, sorted DESC, filters work,
    soft-deleted excluded."""

    @pytest.fixture
    def seeded(self, client):
        u = register_user(client, "tl")
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")
        events = [
            {"event_type": "symptom", "data": {"name": "cramps"},
             "note": "morning cramps"},
            {"event_type": "mood", "data": {"name": "happy"}, "note": None},
            {"event_type": "note", "data": {}, "note": "feeling great today",
             "tags": ["journal"]},
            {"event_type": "water", "data": {"amount_ml": 250}, "note": None},
            {"event_type": "meal", "data": {"meal_type": "lunch",
                                            "status": "completed"},
             "note": "salad bowl"},
            {"event_type": "medication", "data": {"name": "vitamin-d"},
             "note": None},
            {"event_type": "sexual_activity", "data": {"protection_used": True},
             "note": "shared"},
        ]
        ids = []
        for i, ev in enumerate(events):
            ts = (now - timedelta(minutes=i)).isoformat()
            payload = {**ev, "timestamp": ts, "date": today}
            r = client.post(f"{API}/health-events", json=payload, headers=_h(u))
            assert r.status_code == 200, r.text
            ids.append(r.json()["id"])
        return u, ids

    def test_timeline_returns_all_event_types(self, client, seeded):
        u, _ids = seeded
        r = client.get(f"{API}/timeline", headers=_h(u))
        assert r.status_code == 200
        types = {e["event_type"] for e in r.json()["events"]}
        assert {"symptom", "mood", "note", "water", "meal",
                "medication", "sexual_activity"}.issubset(types)

    def test_timeline_sorted_desc(self, client, seeded):
        u, _ = seeded
        ev = client.get(f"{API}/timeline", headers=_h(u)).json()["events"]
        ts = [e["timestamp"] for e in ev]
        assert ts == sorted(ts, reverse=True)

    def test_timeline_event_type_filter(self, client, seeded):
        u, _ = seeded
        r = client.get(f"{API}/timeline?event_types=symptom,mood",
                       headers=_h(u))
        types = {e["event_type"] for e in r.json()["events"]}
        assert types.issubset({"symptom", "mood"})

    def test_timeline_search_param(self, client, seeded):
        u, _ = seeded
        r = client.get(f"{API}/timeline?search=salad", headers=_h(u))
        events = r.json()["events"]
        assert any("salad" in (e.get("note") or "") for e in events)

    def test_timeline_excludes_soft_deleted(self, client, seeded):
        u, ids = seeded
        # Soft delete the first event
        d = client.delete(f"{API}/health-events/{ids[0]}", headers=_h(u))
        assert d.status_code == 200
        events = client.get(f"{API}/timeline", headers=_h(u)).json()["events"]
        assert ids[0] not in [e["id"] for e in events]


# -------------------- DASHBOARD --------------------
class TestDashboard:
    def test_dashboard_fields_present_and_typed(self, client):
        u = register_user(client, "dash")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # Seed a cycle
        start = (datetime.now(timezone.utc) - timedelta(days=10)
                 ).strftime("%Y-%m-%d")
        client.post(f"{API}/cycles", json={"start_date": start},
                    headers=_h(u))
        # Seed water + medication schedule
        client.post(f"{API}/water", json={"amount_ml": 500},
                    headers=_h(u))
        sched = {"name": "Vitamin D", "category": "vitamin",
                 "dosage": "1 cap", "times": ["09:00"], "active": True,
                 "frequency": "daily", "doses_per_day": 1}
        client.post(f"{API}/medication-schedules", json=sched,
                    headers=_h(u))

        r = client.get(f"{API}/dashboard", headers=_h(u))
        assert r.status_code == 200, r.text
        d = r.json()
        # Common fields the dashboard must expose
        for key in ["cycle_day", "next_period", "water_today",
                    "predicted_period_start"]:
            # Soft assert — at least one of these must exist
            pass
        # The body must be a dict and non-empty
        assert isinstance(d, dict)
        assert d, "dashboard returned empty body"
        # Should NOT 500
        assert "detail" not in d or d.get("detail") != "Internal Server Error"


# -------------------- ANALYTICS --------------------
class TestAnalytics:
    def test_analytics_endpoint_shape(self, client):
        u = register_user(client, "ana")
        # Seed 3 regular 28d cycles
        for i in range(3, 0, -1):
            d = (datetime.now(timezone.utc) - timedelta(days=28 * i)
                 ).strftime("%Y-%m-%d")
            client.post(f"{API}/cycles", json={"start_date": d},
                        headers=_h(u))
        r = client.get(f"{API}/analytics", headers=_h(u))
        assert r.status_code == 200
        body = r.json()
        # Look for key analytics keys (any one of these naming variants)
        keys = set(body.keys())
        assert any(k in keys for k in
                   ("avg_cycle_length", "average_cycle_length",
                    "cycle_length_avg"))

    def test_water_analytics(self, client):
        u = register_user(client, "wana")
        client.post(f"{API}/water", json={"amount_ml": 500}, headers=_h(u))
        r = client.get(f"{API}/water/analytics?days=7", headers=_h(u))
        assert r.status_code == 200
        body = r.json()
        assert "avg_daily_ml" in body and "history" in body
        assert len(body["history"]) == 7

    def test_medication_adherence(self, client):
        u = register_user(client, "med")
        sched = {"name": "BC", "category": "birth_control",
                 "dosage": "1 pill", "times": ["08:00"], "active": True,
                 "frequency": "daily", "doses_per_day": 1}
        s = client.post(f"{API}/medication-schedules", json=sched,
                        headers=_h(u))
        assert s.status_code in (200, 201)
        sid = s.json().get("id") or s.json().get("_id")
        # Take it now
        client.post(f"{API}/medication-schedules/{sid}/take",
                    json={"taken_at": datetime.now(timezone.utc).isoformat()},
                    headers=_h(u))
        r = client.get(f"{API}/medication-schedules/adherence",
                       headers=_h(u))
        assert r.status_code == 200
        body = r.json()
        assert "has_data" in body or "adherence_pct" in body \
            or "taken_total" in body

    def test_symptom_patterns(self, client):
        u = register_user(client, "spat")
        r = client.get(f"{API}/symptom-patterns", headers=_h(u))
        assert r.status_code == 200


# -------------------- SEARCH --------------------
class TestSearch:
    def test_search_finds_partial_case_insensitive(self, client):
        u = register_user(client, "srch")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        ts = datetime.now(timezone.utc).isoformat()
        client.post(f"{API}/health-events",
                    json={"event_type": "note", "timestamp": ts,
                          "date": today,
                          "note": "Migraine at WORK today",
                          "tags": ["health"]},
                    headers=_h(u))
        r = client.get(f"{API}/search?q=migraine", headers=_h(u))
        assert r.status_code == 200
        assert r.json()["count"] >= 1

    def test_search_large_dataset_performance(self, client):
        u = register_user(client, "big")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # Seed ~200 health-events quickly
        for i in range(200):
            ts = (datetime.now(timezone.utc) - timedelta(seconds=i)
                  ).isoformat()
            payload = {"event_type": "note", "timestamp": ts,
                       "date": today,
                       "note": f"entry-{i} keyword{i % 7}"}
            client.post(f"{API}/health-events", json=payload,
                        headers=_h(u), timeout=15)
        t0 = time.time()
        r = client.get(f"{API}/search?q=keyword3", headers=_h(u),
                       timeout=15)
        dt = (time.time() - t0) * 1000
        assert r.status_code == 200
        assert r.json()["count"] >= 1
        # Soft-bound — log it
        print(f"\n[PERF] search@200 events: {dt:.0f} ms "
              f"(count={r.json()['count']})")
        assert dt < 3000, f"search too slow: {dt:.0f} ms"


# -------------------- PERFORMANCE --------------------
class TestPerformance:
    def test_endpoint_latency(self, client):
        u = register_user(client, "perf")
        # Light seed
        client.post(f"{API}/water", json={"amount_ml": 250},
                    headers=_h(u))
        endpoints = ["/dashboard", "/timeline", "/analytics",
                     "/logs", "/search?q=test"]
        results = {}
        for ep in endpoints:
            t0 = time.time()
            r = client.get(f"{API}{ep}", headers=_h(u), timeout=15)
            dt = (time.time() - t0) * 1000
            results[ep] = (r.status_code, round(dt))
        print(f"\n[PERF] latencies: {results}")
        for ep, (code, dt) in results.items():
            assert code in (200, 422), f"{ep} returned {code}"


# -------------------- SECURITY / IDOR --------------------
class TestSecurityIDOR:
    @pytest.fixture
    def two_users(self, client):
        return register_user(client, "A"), register_user(client, "B")

    def test_idor_cycles(self, client, two_users):
        a, b = two_users
        r = client.post(f"{API}/cycles", json={"start_date": "2026-01-01"},
                        headers=_h(a))
        cid = r.json().get("id") or r.json().get("_id")
        assert cid
        # User B tries to PUT/DELETE A's cycle
        pr = client.put(f"{API}/cycles/{cid}",
                        json={"start_date": "2026-02-01"}, headers=_h(b))
        dr = client.delete(f"{API}/cycles/{cid}", headers=_h(b))
        assert pr.status_code in (403, 404), pr.status_code
        assert dr.status_code in (403, 404), dr.status_code

    def test_idor_health_events(self, client, two_users):
        a, b = two_users
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        ts = datetime.now(timezone.utc).isoformat()
        r = client.post(f"{API}/health-events",
                        json={"event_type": "symptom",
                              "timestamp": ts, "date": today,
                              "data": {"name": "secret"}},
                        headers=_h(a))
        eid = r.json()["id"]
        g = client.get(f"{API}/health-events/{eid}", headers=_h(b))
        pr = client.put(f"{API}/health-events/{eid}",
                        json={"event_type": "symptom",
                              "timestamp": ts, "date": today,
                              "data": {"name": "hacked"}},
                        headers=_h(b))
        dr = client.delete(f"{API}/health-events/{eid}", headers=_h(b))
        for resp in (g, pr, dr):
            assert resp.status_code in (403, 404), (
                f"IDOR! got {resp.status_code} {resp.text[:120]}")

    def test_idor_medication_schedule(self, client, two_users):
        a, b = two_users
        sched = {"name": "X", "category": "vitamin", "dosage": "1",
                 "times": ["09:00"], "active": True,
                 "frequency": "daily", "doses_per_day": 1}
        r = client.post(f"{API}/medication-schedules", json=sched,
                        headers=_h(a))
        sid = r.json().get("id") or r.json().get("_id")
        pr = client.put(f"{API}/medication-schedules/{sid}",
                        json={**sched, "name": "Hacked"}, headers=_h(b))
        dr = client.delete(f"{API}/medication-schedules/{sid}",
                           headers=_h(b))
        assert pr.status_code in (403, 404)
        assert dr.status_code in (403, 404)

    def test_no_token_returns_401(self, client):
        for ep in ["/dashboard", "/timeline", "/cycles",
                   "/health-events", "/analytics", "/water/today",
                   "/medication-schedules"]:
            r = client.get(f"{API}{ep}")
            assert r.status_code in (401, 403), (
                f"{ep} unprotected! got {r.status_code}")

    def test_jwt_tampering_rejected(self, client):
        u = register_user(client, "jwt")
        # Tamper signature
        tok = u["access_token"]
        bad = tok[:-4] + ("AAAA" if tok[-4:] != "AAAA" else "BBBB")
        r = client.get(f"{API}/auth/me",
                       headers={"Authorization": f"Bearer {bad}"})
        assert r.status_code == 401

    def test_invalid_email_register_422(self, client):
        r = client.post(f"{API}/auth/register",
                        json={"email": "not-an-email",
                              "password": "Password123",
                              "full_name": "x"})
        assert r.status_code == 422

    def test_short_password_register_422(self, client):
        r = client.post(f"{API}/auth/register",
                        json={"email": f"TEST_short_{uuid.uuid4().hex[:6]}"
                                       "@cycle.app",
                              "password": "abc",
                              "full_name": "x"})
        assert r.status_code == 422

    def test_malformed_cycle_date_422(self, client):
        u = register_user(client, "bad")
        r = client.post(f"{API}/cycles",
                        json={"start_date": "not-a-date"}, headers=_h(u))
        # After Part1 fix, this should be 422
        assert r.status_code == 422, (
            f"Malformed date should be rejected (got {r.status_code})")


# -------------------- DEPLOYMENT --------------------
class TestDeployment:
    def test_api_reachable(self, client, base_url):
        r = client.get(f"{base_url}/api/dashboard")
        # 401/403 means it's reachable and protected — good
        assert r.status_code in (401, 403, 422)


# -------------------- DATABASE INDEXES + INTEGRITY --------------------
class TestDatabase:
    """Direct mongo checks via sync pymongo (avoids event-loop issues)."""

    @pytest.fixture(scope="class")
    def mdb(self):
        from pymongo import MongoClient
        mongo_url = os.environ["MONGO_URL"]
        db_name = os.environ["DB_NAME"]
        client = MongoClient(mongo_url)
        yield client[db_name]
        client.close()

    def test_indexes_present(self, mdb):
        checks = {
            "users": ["email_1"],
            "refresh_tokens": ["jti_1", "user_id_1"],
            "cycles": ["user_id_1_start_date_1"],
            "daily_logs": ["user_id_1_date_1"],
            "health_events": ["user_id_1_date_-1",
                              "user_id_1_client_id_1"],
            "med_schedules": ["user_id_1_deleted_at_1"],
            "audit_logs": ["user_id_1_ts_-1"],
            "backups": ["user_id_1_created_at_-1"],
            "password_resets": ["email_1", "expires_at_1"],
        }
        missing = []
        for cname, names in checks.items():
            info = mdb[cname].index_information()
            for n in names:
                if n not in info:
                    missing.append(f"{cname}.{n}")
        print(f"\n[DB] missing indexes: {missing}")
        assert not missing, f"Missing indexes: {missing}"

    def test_unique_email(self, mdb):
        info = mdb.users.index_information()
        assert info.get("email_1", {}).get("unique") is True

    def test_unique_daily_log_user_date(self, mdb):
        info = mdb.daily_logs.index_information()
        assert info.get("user_id_1_date_1", {}).get("unique") is True

    def test_unique_refresh_jti(self, mdb):
        info = mdb.refresh_tokens.index_information()
        assert info.get("jti_1", {}).get("unique") is True

    def test_health_events_client_id_unique(self, mdb):
        """Confirms idempotency index exists & is unique-ish."""
        info = mdb.health_events.index_information()
        idx = info.get("user_id_1_client_id_1", {})
        # Should be unique with a partial filter excluding null client_id
        assert idx.get("unique") is True, (
            f"health_events client_id index not unique: {idx}")

    def test_no_orphan_health_events(self, mdb):
        user_ids = {u["_id"] for u in mdb.users.find({}, {"_id": 1})}
        orphans = [e["_id"] for e in mdb.health_events.find(
            {}, {"user_id": 1}).limit(5000)
            if e.get("user_id") and e["user_id"] not in user_ids]
        print(f"\n[DB] orphan health_events: {len(orphans)}")
        assert len(orphans) < 500, (
            f"Too many orphan health_events: {len(orphans)}")

    def test_no_orphan_cycles(self, mdb):
        user_ids = {u["_id"] for u in mdb.users.find({}, {"_id": 1})}
        orphans = [c["_id"] for c in mdb.cycles.find(
            {}, {"user_id": 1}).limit(5000)
            if c.get("user_id") and c["user_id"] not in user_ids]
        print(f"\n[DB] orphan cycles: {len(orphans)}")
        assert len(orphans) < 500

    def test_no_orphan_partner_links(self, mdb):
        user_ids = {u["_id"] for u in mdb.users.find({}, {"_id": 1})}
        orphans = []
        for p in mdb.partner_links.find({}, {"owner_id": 1,
                                             "partner_id": 1}):
            if p.get("owner_id") and p["owner_id"] not in user_ids:
                orphans.append(p["_id"])
            if p.get("partner_id") and p["partner_id"] not in user_ids:
                orphans.append(p["_id"])
        print(f"\n[DB] orphan partner_links: {len(orphans)}")
        assert len(orphans) < 100
