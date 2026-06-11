"""In-app account Backup & Restore (server-side snapshots, no files).

A backup is an embedded snapshot of the user's health data (cycles, daily logs,
health events, medication schedules). Restore wipes the user's current data in those
collections and re-inserts the snapshot copies (original ids preserved so references
like health_event.data.schedule_id stay valid). Restore is destructive — confirm in UI.
"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

import db
from audit import record_audit
from auth import get_current_user, now_utc

router = APIRouter(prefix="/api")

# Collections included in a backup snapshot.
SNAPSHOT_COLLECTIONS = ["cycles", "daily_logs", "health_events", "med_schedules"]
AUTO_BACKUP_INTERVAL_DAYS = 7


def _coll(name: str):
    return getattr(db, name)


async def _make_backup(uid: str, backup_type: str) -> dict:
    """Create a backup snapshot of the user's data and return a summary."""
    snapshot: dict = {}
    counts: dict = {}
    for name in SNAPSHOT_COLLECTIONS:
        docs = await _coll(name).find({"user_id": uid}).to_list(100000)
        snapshot[name] = docs
        counts[name] = len(docs)

    backup_id = str(uuid.uuid4())
    created_iso = datetime.now(timezone.utc).isoformat()
    await db.backups.insert_one({
        "_id": backup_id,
        "user_id": uid,
        "type": backup_type,            # "manual" | "auto"
        "created_at": created_iso,
        "counts": counts,
        "snapshot": snapshot,
    })
    return {"id": backup_id, "type": backup_type, "created_at": created_iso,
            "counts": counts, "total": sum(counts.values())}


@router.post("/backup")
async def create_backup(current=Depends(get_current_user)):
    uid = current["_id"]
    result = await _make_backup(uid, "manual")
    await record_audit(uid, "backed_up", "backup", result["id"],
                       f"Backup created ({result['total']} records)")
    return result


@router.post("/backups/ensure-weekly")
async def ensure_weekly_backup(current=Depends(get_current_user)):
    """Create a weekly automatic backup if the latest auto-backup is missing or >7 days old.

    Keeps only the newest auto-backup (replaces older auto ones); manual backups are untouched.
    Safe to call on every app launch — it no-ops when a recent auto-backup already exists.
    """
    uid = current["_id"]
    latest_auto = await db.backups.find_one(
        {"user_id": uid, "type": "auto"},
        sort=[("created_at", -1)],
    )
    if latest_auto:
        try:
            last = datetime.fromisoformat(latest_auto["created_at"])
            age_days = (datetime.now(timezone.utc) - last).days
        except Exception:
            age_days = AUTO_BACKUP_INTERVAL_DAYS
        if age_days < AUTO_BACKUP_INTERVAL_DAYS:
            return {"created": False, "reason": "recent_auto_backup_exists"}

    result = await _make_backup(uid, "auto")
    # Replace older auto-backups — keep only the one we just made.
    await db.backups.delete_many(
        {"user_id": uid, "type": "auto", "_id": {"$ne": result["id"]}})
    await record_audit(uid, "backed_up", "backup", result["id"],
                       f"Automatic weekly backup ({result['total']} records)")
    return {"created": True, **result}


@router.get("/backups")
async def list_backups(current=Depends(get_current_user)):
    rows = await db.backups.find(
        {"user_id": current["_id"]},
        {"snapshot": 0, "user_id": 0},
    ).sort("created_at", -1).to_list(100)
    out = []
    for r in rows:
        counts = r.get("counts", {})
        out.append({
            "id": r["_id"],
            "type": r.get("type", "manual"),
            "created_at": r.get("created_at"),
            "counts": counts,
            "total": sum(counts.values()) if counts else 0,
        })
    return out


@router.post("/backups/{backup_id}/restore")
async def restore_backup(backup_id: str, current=Depends(get_current_user)):
    uid = current["_id"]
    backup = await db.backups.find_one({"_id": backup_id, "user_id": uid})
    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")

    snapshot = backup.get("snapshot", {})
    restored: dict = {}
    for name in SNAPSHOT_COLLECTIONS:
        coll = _coll(name)
        await coll.delete_many({"user_id": uid})
        docs = snapshot.get(name, [])
        if docs:
            # Re-insert copies so the original backup remains intact for future restores.
            await coll.insert_many([dict(d) for d in docs])
        restored[name] = len(docs)

    await record_audit(uid, "restored", "backup", backup_id,
                       f"Restored backup ({sum(restored.values())} records)")
    return {"restored": restored, "total": sum(restored.values())}


@router.delete("/backups/{backup_id}")
async def delete_backup(backup_id: str, current=Depends(get_current_user)):
    res = await db.backups.delete_one({"_id": backup_id, "user_id": current["_id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Backup not found")
    return {"detail": "deleted"}
