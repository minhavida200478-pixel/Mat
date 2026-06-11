"""Backend tests for DATA PROTECTION endpoints:
- /api/audit-logs  (append-only change history feed)
- /api/backup, /api/backups, /api/backups/{id}/restore, /api/backups/{id} (Backup & Restore)

Each test registers a fresh user to keep data isolated (restore is destructive).
"""
import os
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

# Load frontend .env for public preview URL.
load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")

BASE_URL = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("EXPO_BACKEND_URL")
    or ""
).rstrip("/")
API = f"{BASE_URL}/api"


def _auth(headers_or_user):
    """Accept either a token string, a {access_token} dict, or the fresh_user fixture."""
    if isinstance(headers_or_user, dict) and "access_token" in headers_or_user:
        return {
            "Authorization": f"Bearer {headers_or_user['access_token']}",
            "Content-Type": "application/json",
        }
    return headers_or_user


# ---------- Auth enforcement ----------
class TestAuthEnforcement:
    def test_audit_logs_requires_auth(self):
        r = requests.get(f"{API}/audit-logs", timeout=15)
        assert r.status_code in (401, 403), f"got {r.status_code} {r.text}"

    def test_create_backup_requires_auth(self):
        r = requests.post(f"{API}/backup", json={}, timeout=15)
        assert r.status_code in (401, 403)

    def test_list_backups_requires_auth(self):
        r = requests.get(f"{API}/backups", timeout=15)
        assert r.status_code in (401, 403)


# ---------- Audit log feed ----------
class TestAuditLogs:
    def test_audit_records_activity(self, client, fresh_user):
        h = _auth(fresh_user)

        # Create a cycle.
        r = client.post(f"{API}/cycles",
                        json={"start_date": "2026-01-01"}, headers=h, timeout=15)
        assert r.status_code in (200, 201), r.text

        # Save a daily log (endpoint is POST /api/logs — daily log upsert).
        r2 = client.post(
            f"{API}/logs",
            json={
                "date": "2026-01-02",
                "symptoms": [],
                "moods": ["happy"],
                "note": "feeling good",
                "tags": [],
                "visibility": "private",
            },
            headers=h, timeout=15,
        )
        assert r2.status_code in (200, 201), r2.text

        # Create a medication schedule (POST /api/medication-schedules).
        med_payload = {
            "name": "TEST_AuditMed",
            "schedule_type": "daily",
            "times": ["09:00"],
            "enabled": True,
        }
        r3 = client.post(f"{API}/medication-schedules",
                         json=med_payload, headers=h, timeout=15)
        assert r3.status_code in (200, 201), r3.text

        # Now fetch the audit feed.
        r4 = client.get(f"{API}/audit-logs?limit=50", headers=h, timeout=15)
        assert r4.status_code == 200, r4.text
        feed = r4.json()
        assert isinstance(feed, dict)
        assert "items" in feed and "next_before" in feed
        items = feed["items"]
        assert isinstance(items, list)
        assert len(items) >= 3, f"expected >=3 audit rows, got {len(items)}: {items}"

        entity_types = {it.get("entity_type") for it in items}
        actions = {it.get("action") for it in items}
        # At minimum cycle + medication entries should show up.
        assert "cycle" in entity_types, f"missing 'cycle' in entities: {entity_types}"
        assert "medication" in entity_types, f"missing 'medication' in entities: {entity_types}"
        assert "created" in actions, f"missing 'created' action: {actions}"

        # Each row must have ts/action/entity_type/summary keys.
        for it in items[:5]:
            for k in ("ts", "action", "entity_type", "summary"):
                assert k in it, f"row missing '{k}': {it}"

    def test_audit_filter_by_entity_type(self, client, fresh_user):
        h = _auth(fresh_user)
        # create a cycle so there's at least one cycle audit entry
        client.post(f"{API}/cycles", json={"start_date": "2026-01-03"}, headers=h, timeout=15)
        r = client.get(f"{API}/audit-logs?entity_type=cycle&limit=20", headers=h, timeout=15)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 1
        assert all(it["entity_type"] == "cycle" for it in items)

    def test_audit_pagination_cursor(self, client, fresh_user):
        h = _auth(fresh_user)
        # generate >2 entries by creating multiple cycles
        for d in ("2026-02-01", "2026-02-15", "2026-03-01", "2026-03-15"):
            client.post(f"{API}/cycles", json={"start_date": d}, headers=h, timeout=15)
        r = client.get(f"{API}/audit-logs?limit=2", headers=h, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert len(body["items"]) == 2
        # cursor present when page is full
        assert body["next_before"], "expected next_before cursor when len(items)==limit"

        # Fetch the second page
        nb = body["next_before"]
        r2 = client.get(f"{API}/audit-logs?limit=2&before={nb}", headers=h, timeout=15)
        assert r2.status_code == 200
        page2 = r2.json()["items"]
        # Page 2 entries must have ts strictly < cursor
        for it in page2:
            assert it["ts"] < nb


# ---------- Backup & Restore ----------
class TestBackupRestore:
    def test_create_list_delete_backup(self, client, fresh_user):
        h = _auth(fresh_user)
        # seed: one cycle so counts are non-zero
        client.post(f"{API}/cycles", json={"start_date": "2026-04-01"}, headers=h, timeout=15)

        # Create backup
        r = client.post(f"{API}/backup", json={}, headers=h, timeout=20)
        assert r.status_code in (200, 201), r.text
        body = r.json()
        for k in ("id", "created_at", "counts", "total"):
            assert k in body, f"missing key '{k}': {body}"
        counts = body["counts"]
        for k in ("cycles", "daily_logs", "health_events", "med_schedules"):
            assert k in counts, f"missing count '{k}': {counts}"
        assert body["total"] == sum(counts.values())
        assert counts["cycles"] >= 1
        bid = body["id"]

        # List backups
        rl = client.get(f"{API}/backups", headers=h, timeout=15)
        assert rl.status_code == 200
        rows = rl.json()
        assert isinstance(rows, list)
        found = next((r for r in rows if r["id"] == bid), None)
        assert found, f"created backup {bid} missing from list"
        # snapshot must NOT be exposed in list response
        assert "snapshot" not in found
        assert "counts" in found and "total" in found

        # Delete backup
        rd = client.delete(f"{API}/backups/{bid}", headers=h, timeout=15)
        assert rd.status_code == 200, rd.text
        # Verify gone via list
        rl2 = client.get(f"{API}/backups", headers=h, timeout=15)
        assert all(r["id"] != bid for r in rl2.json())
        # Re-delete -> 404
        rd2 = client.delete(f"{API}/backups/{bid}", headers=h, timeout=15)
        assert rd2.status_code == 404

    def test_restore_replaces_current_data(self, client, fresh_user):
        """Create a cycle -> backup -> delete the cycle -> restore -> verify cycle is back."""
        h = _auth(fresh_user)

        # 1. Create a cycle
        rc = client.post(f"{API}/cycles", json={"start_date": "2026-05-01"}, headers=h, timeout=15)
        assert rc.status_code in (200, 201), rc.text
        cycle = rc.json()
        cid = cycle.get("id") or cycle.get("_id")
        assert cid, f"cycle response missing id: {cycle}"

        # 2. Create backup containing this cycle
        rb = client.post(f"{API}/backup", json={}, headers=h, timeout=20)
        assert rb.status_code in (200, 201), rb.text
        backup_id = rb.json()["id"]
        assert rb.json()["counts"]["cycles"] >= 1

        # 3. Delete the cycle
        rd = client.delete(f"{API}/cycles/{cid}", headers=h, timeout=15)
        assert rd.status_code in (200, 204), rd.text
        # Verify gone
        rg = client.get(f"{API}/cycles", headers=h, timeout=15)
        assert rg.status_code == 200
        cycles_now = rg.json()
        assert all((c.get("id") or c.get("_id")) != cid for c in cycles_now), \
            "cycle still present after delete"

        # 4. Restore
        rr = client.post(f"{API}/backups/{backup_id}/restore", json={}, headers=h, timeout=30)
        assert rr.status_code == 200, rr.text
        restored = rr.json()
        assert restored.get("total", 0) >= 1
        assert restored.get("restored", {}).get("cycles", 0) >= 1

        # 5. Verify cycle is back
        rg2 = client.get(f"{API}/cycles", headers=h, timeout=15)
        assert rg2.status_code == 200
        cycles_after = rg2.json()
        assert any((c.get("id") or c.get("_id")) == cid for c in cycles_after), \
            f"restored cycle {cid} not found. got: {cycles_after}"

        # Cleanup: delete the backup we created so we don't litter the DB
        client.delete(f"{API}/backups/{backup_id}", headers=h, timeout=15)

    def test_restore_unknown_backup_returns_404(self, client, fresh_user):
        h = _auth(fresh_user)
        r = client.post(f"{API}/backups/does-not-exist/restore", json={}, headers=h, timeout=15)
        assert r.status_code == 404

    def test_backup_creates_audit_entry(self, client, fresh_user):
        h = _auth(fresh_user)
        rb = client.post(f"{API}/backup", json={}, headers=h, timeout=20)
        assert rb.status_code in (200, 201)
        bid = rb.json()["id"]

        # Fetch audit feed and confirm a backup row exists.
        r = client.get(f"{API}/audit-logs?entity_type=backup&limit=10",
                       headers=h, timeout=15)
        assert r.status_code == 200
        items = r.json()["items"]
        assert any(it.get("action") == "backed_up" and it.get("entity_id") == bid
                   for it in items), f"no 'backed_up' audit row for {bid}: {items}"

        # cleanup
        client.delete(f"{API}/backups/{bid}", headers=h, timeout=15)
