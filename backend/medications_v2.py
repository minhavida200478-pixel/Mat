"""Smart Medication Reminders + Adherence.

Stores medication *schedules* (daily / every-X-hours / cycle-day based) and computes
adherence statistics by matching scheduled doses against logged "taken" events.

Doses taken are recorded as unified health events (event_type="medication") that carry
data.schedule_id + data.scheduled_time so adherence can reconcile planned vs. taken.
"""
import bisect
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

import db
from audit import record_audit
from auth import get_current_user, now_utc

router = APIRouter(prefix="/api")

ScheduleType = Literal["daily", "interval", "cycle_based"]
MedCategory = Literal["painkiller", "birth_control", "vitamin", "supplement", "hormone", "other"]


# ----------------------------- Models -----------------------------
class MedicationScheduleIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    dosage: Optional[str] = None
    category: MedCategory = "other"
    schedule_type: ScheduleType = "daily"
    times: List[str] = []              # ["08:00", "21:00"] (daily / cycle_based)
    interval_hours: Optional[int] = None   # interval type: every X hours
    interval_start: Optional[str] = "08:00"  # interval type: first dose time
    cycle_days: List[int] = []         # cycle_based: which cycle days to take (1-based)
    enabled: bool = True


class MarkTakenIn(BaseModel):
    scheduled_time: Optional[str] = None  # "08:00" the planned slot this fulfils
    timestamp: Optional[str] = None       # ISO datetime; defaults to now
    client_id: Optional[str] = None       # offline-sync idempotency key


# ----------------------------- Helpers -----------------------------
def _parse_d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _hhmm_to_minutes(t: str) -> int:
    try:
        h, m = t.split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return 0


def _compute_interval_times(start: str, interval_hours: int) -> List[str]:
    """Expand an "every X hours from start" rule into discrete daily HH:MM slots."""
    if not interval_hours or interval_hours <= 0:
        return []
    start_min = _hhmm_to_minutes(start or "08:00")
    times = []
    cur = start_min
    # safety cap of 24 doses
    while cur < 24 * 60 and len(times) < 24:
        times.append(f"{cur // 60:02d}:{cur % 60:02d}")
        cur += interval_hours * 60
    return times


def _normalize_times(payload: MedicationScheduleIn) -> List[str]:
    if payload.schedule_type == "interval":
        return _compute_interval_times(payload.interval_start or "08:00",
                                       payload.interval_hours or 0)
    # daily / cycle_based: dedupe + sort the provided times
    seen = sorted({t for t in payload.times if t}, key=_hhmm_to_minutes)
    return seen


def schedule_out(doc: dict) -> dict:
    return {
        "id": doc["_id"],
        "name": doc["name"],
        "dosage": doc.get("dosage"),
        "category": doc.get("category", "other"),
        "schedule_type": doc.get("schedule_type", "daily"),
        "times": doc.get("times", []),
        "interval_hours": doc.get("interval_hours"),
        "interval_start": doc.get("interval_start"),
        "cycle_days": doc.get("cycle_days", []),
        "enabled": doc.get("enabled", True),
    }


async def _cycle_day_for(user_id: str, target: date) -> Optional[int]:
    """Cycle day (1-based) for a date, based on the most recent prior period start."""
    row = await db.cycles.find_one(
        {"user_id": user_id, "deleted_at": None,
         "start_date": {"$lte": target.isoformat()}},
        sort=[("start_date", -1)],
    )
    if not row:
        return None
    return (target - _parse_d(row["start_date"])).days + 1


async def _expected_doses_on(sched: dict, user_id: str, target: date,
                             cycle_day_cache: dict) -> List[str]:
    """Return the list of planned HH:MM slots for this schedule on the given date."""
    times = sched.get("times", []) or []
    if sched.get("schedule_type") == "cycle_based":
        cd = cycle_day_cache.get(target.isoformat(), "missing")
        if cd == "missing":
            cd = await _cycle_day_for(user_id, target)
            cycle_day_cache[target.isoformat()] = cd
        if cd is None or cd not in (sched.get("cycle_days") or []):
            return []
    return times


async def _taken_count(user_id: str, schedule_id: str, day: str) -> int:
    return await db.health_events.count_documents({
        "user_id": user_id, "event_type": "medication", "date": day,
        "deleted_at": None, "data.schedule_id": schedule_id,
    })


async def _build_cycle_day_map(user_id: str, start: date, end: date) -> dict:
    """Precompute cycle-day (1-based) for every date in [start, end] with ONE query.

    Replaces the per-date _cycle_day_for() DB round-trips: we fetch all of the user's
    period starts once, then resolve each date's cycle day in-memory via binary search
    (most recent start on or before that date).
    """
    rows = await db.cycles.find(
        {"user_id": user_id, "deleted_at": None},
        {"_id": 0, "start_date": 1},
    ).sort("start_date", 1).to_list(2000)
    starts: List[date] = []
    for r in rows:
        try:
            starts.append(_parse_d(r["start_date"]))
        except (ValueError, TypeError):
            continue  # skip malformed legacy rows
    cmap: dict = {}
    cur = start
    while cur <= end:
        idx = bisect.bisect_right(starts, cur) - 1
        cmap[cur.isoformat()] = ((cur - starts[idx]).days + 1) if idx >= 0 else None
        cur += timedelta(days=1)
    return cmap


def _expected_doses_sync(sched: dict, target: date, cycle_day_map: dict) -> List[str]:
    """Planned HH:MM slots for a schedule on a date, using a precomputed cycle-day map
    (no DB access — the async _expected_doses_on equivalent for batch adherence)."""
    times = sched.get("times", []) or []
    if sched.get("schedule_type") == "cycle_based":
        cd = cycle_day_map.get(target.isoformat())
        if cd is None or cd not in (sched.get("cycle_days") or []):
            return []
    return times


async def _taken_by_sched_date(user_id: str, start_iso: str, end_iso: str) -> dict:
    """Bucket "taken" medication events into {(schedule_id, date): count} with ONE
    aggregation, replacing the per-(schedule, day) count_documents calls."""
    pipeline = [
        {"$match": {
            "user_id": user_id, "event_type": "medication", "deleted_at": None,
            "date": {"$gte": start_iso, "$lte": end_iso},
            "data.schedule_id": {"$exists": True},
        }},
        {"$group": {
            "_id": {"schedule_id": "$data.schedule_id", "date": "$date"},
            "count": {"$sum": 1},
        }},
    ]
    out: dict = {}
    async for row in db.health_events.aggregate(pipeline):
        key = (row["_id"].get("schedule_id"), row["_id"].get("date"))
        out[key] = row["count"]
    return out


# ----------------------------- CRUD -----------------------------
@router.post("/medication-schedules")
async def create_schedule(payload: MedicationScheduleIn, current=Depends(get_current_user)):
    times = _normalize_times(payload)
    if payload.schedule_type != "interval" and not times:
        raise HTTPException(status_code=400, detail="Add at least one time for this schedule")
    if payload.schedule_type == "interval" and not times:
        raise HTTPException(status_code=400, detail="Set a valid interval and start time")
    if payload.schedule_type == "cycle_based" and not payload.cycle_days:
        raise HTTPException(status_code=400, detail="Select at least one cycle day")
    doc = {
        "_id": str(uuid.uuid4()),
        "user_id": current["_id"],
        "name": payload.name.strip(),
        "dosage": (payload.dosage or "").strip() or None,
        "category": payload.category,
        "schedule_type": payload.schedule_type,
        "times": times,
        "interval_hours": payload.interval_hours,
        "interval_start": payload.interval_start,
        "cycle_days": sorted(set(payload.cycle_days)),
        "enabled": payload.enabled,
        "created_at": now_utc(),
        "updated_at": now_utc(),
        "deleted_at": None,
    }
    await db.med_schedules.insert_one(doc)
    await record_audit(current["_id"], "created", "medication", doc["_id"],
                       f"Added medication “{doc['name']}”")
    return schedule_out(doc)


@router.get("/medication-schedules")
async def list_schedules(current=Depends(get_current_user)):
    rows = await db.med_schedules.find(
        {"user_id": current["_id"], "deleted_at": None}
    ).sort("created_at", 1).to_list(200)
    return [schedule_out(r) for r in rows]


@router.put("/medication-schedules/{schedule_id}")
async def update_schedule(schedule_id: str, payload: MedicationScheduleIn,
                          current=Depends(get_current_user)):
    times = _normalize_times(payload)
    if payload.schedule_type != "interval" and not times:
        raise HTTPException(status_code=400, detail="Add at least one time for this schedule")
    if payload.schedule_type == "cycle_based" and not payload.cycle_days:
        raise HTTPException(status_code=400, detail="Select at least one cycle day")
    update = {
        "name": payload.name.strip(),
        "dosage": (payload.dosage or "").strip() or None,
        "category": payload.category,
        "schedule_type": payload.schedule_type,
        "times": times,
        "interval_hours": payload.interval_hours,
        "interval_start": payload.interval_start,
        "cycle_days": sorted(set(payload.cycle_days)),
        "enabled": payload.enabled,
        "updated_at": now_utc(),
    }
    res = await db.med_schedules.update_one(
        {"_id": schedule_id, "user_id": current["_id"], "deleted_at": None},
        {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Medication not found")
    doc = await db.med_schedules.find_one({"_id": schedule_id})
    await record_audit(current["_id"], "updated", "medication", schedule_id,
                       f"Updated medication “{doc['name']}”")
    return schedule_out(doc)


@router.delete("/medication-schedules/{schedule_id}")
async def delete_schedule(schedule_id: str, current=Depends(get_current_user)):
    res = await db.med_schedules.update_one(
        {"_id": schedule_id, "user_id": current["_id"]},
        {"$set": {"deleted_at": now_utc(), "updated_at": now_utc(), "enabled": False}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Medication not found")
    await record_audit(current["_id"], "deleted", "medication", schedule_id,
                       "Deleted a medication & its reminders")
    return {"detail": "deleted"}


# ----------------------------- Today's doses -----------------------------
@router.get("/medication-schedules/today")
async def todays_doses(today: Optional[str] = None, current=Depends(get_current_user)):
    today_str = today or date.today().isoformat()
    target = _parse_d(today_str)
    schedules = await db.med_schedules.find(
        {"user_id": current["_id"], "deleted_at": None, "enabled": True}
    ).to_list(200)

    cache: dict = {}
    doses = []
    total = 0
    taken_total = 0
    for sched in schedules:
        times = await _expected_doses_on(sched, current["_id"], target, cache)
        if not times:
            continue
        taken_events = await db.health_events.find({
            "user_id": current["_id"], "event_type": "medication", "date": today_str,
            "deleted_at": None, "data.schedule_id": sched["_id"],
        }).to_list(100)
        taken_slots = [(e.get("data") or {}).get("scheduled_time") for e in taken_events]
        # Count slots fulfilled; unmatched "taken" still count toward earliest pending slot.
        taken_specific = [s for s in taken_slots if s]
        untagged_taken = len([s for s in taken_slots if not s])
        for t in times:
            total += 1
            is_taken = t in taken_specific
            if is_taken:
                taken_specific.remove(t)
            elif untagged_taken > 0:
                is_taken = True
                untagged_taken -= 1
            if is_taken:
                taken_total += 1
            doses.append({
                "schedule_id": sched["_id"],
                "name": sched["name"],
                "dosage": sched.get("dosage"),
                "category": sched.get("category", "other"),
                "time": t,
                "taken": is_taken,
            })

    doses.sort(key=lambda d: _hhmm_to_minutes(d["time"]))
    return {
        "date": today_str,
        "doses": doses,
        "total": total,
        "taken": taken_total,
        "pending": total - taken_total,
    }


# ----------------------------- Mark taken -----------------------------
@router.post("/medication-schedules/{schedule_id}/take")
async def mark_taken(schedule_id: str, payload: MarkTakenIn, current=Depends(get_current_user)):
    sched = await db.med_schedules.find_one(
        {"_id": schedule_id, "user_id": current["_id"], "deleted_at": None})
    if not sched:
        raise HTTPException(status_code=404, detail="Medication not found")
    ts = payload.timestamp or datetime.now(timezone.utc).isoformat()
    day = ts[:10]
    if payload.client_id:
        existing = await db.health_events.find_one(
            {"user_id": current["_id"], "client_id": payload.client_id})
        if existing:
            return {"detail": "logged", "schedule_id": schedule_id,
                    "scheduled_time": payload.scheduled_time, "deduped": True}
    doc = {
        "_id": str(uuid.uuid4()),
        "user_id": current["_id"],
        "event_type": "medication",
        "timestamp": ts,
        "date": day,
        "data": {
            "name": sched["name"],
            "dosage": sched.get("dosage"),
            "category": sched.get("category", "other"),
            "schedule_id": schedule_id,
            "scheduled_time": payload.scheduled_time,
            "status": "taken",
        },
        "note": None,
        "visibility": "private",
        "tags": [],
        "created_by": current["_id"],
        "created_by_type": "user",
        "client_id": payload.client_id,
        "created_at": now_utc(),
        "updated_at": now_utc(),
        "deleted_at": None,
    }
    await db.health_events.insert_one(doc)
    return {"detail": "logged", "schedule_id": schedule_id, "scheduled_time": payload.scheduled_time}


# ----------------------------- Adherence -----------------------------
@router.get("/medication-schedules/adherence")
async def adherence(days: int = Query(default=30, ge=7, le=90),
                    today: Optional[str] = None, current=Depends(get_current_user)):
    today_str = today or date.today().isoformat()
    end = _parse_d(today_str)
    start = end - timedelta(days=days - 1)

    schedules = await db.med_schedules.find(
        {"user_id": current["_id"], "deleted_at": None, "enabled": True}
    ).to_list(200)

    per_sched = {s["_id"]: {"name": s["name"], "dosage": s.get("dosage"),
                            "category": s.get("category", "other"),
                            "expected": 0, "taken": 0} for s in schedules}

    overall_expected = 0
    overall_taken = 0
    # day -> {expected, taken} for streak + recent bars
    day_stats: dict = {}

    # Two batch reads replace the old O(days × schedules) DB round-trips:
    #   1) cycle-day map for the whole window (for cycle_based schedules)
    #   2) taken-event counts grouped by (schedule_id, date)
    cycle_day_map = await _build_cycle_day_map(current["_id"], start, end)
    taken_map = await _taken_by_sched_date(
        current["_id"], start.isoformat(), end.isoformat())

    cur = start
    while cur <= end:
        d_iso = cur.isoformat()
        day_exp = 0
        day_taken = 0
        for sched in schedules:
            created = sched.get("created_at")
            if isinstance(created, datetime) and created.date() > cur:
                continue  # schedule didn't exist yet on this date
            times = _expected_doses_sync(sched, cur, cycle_day_map)
            exp = len(times)
            if exp == 0:
                continue
            taken = min(taken_map.get((sched["_id"], d_iso), 0), exp)  # cap at expected
            per_sched[sched["_id"]]["expected"] += exp
            per_sched[sched["_id"]]["taken"] += taken
            day_exp += exp
            day_taken += taken
        day_stats[d_iso] = {"expected": day_exp, "taken": day_taken}
        overall_expected += day_exp
        overall_taken += day_taken
        cur += timedelta(days=1)

    # Streak: consecutive days with doses scheduled where every dose was taken,
    # ending today (or yesterday — grace for today). Days with nothing scheduled
    # are skipped (they neither add to nor break the streak).
    def _has_doses(stat) -> bool:
        return stat["expected"] > 0

    def _complete(stat) -> bool:
        return stat["taken"] >= stat["expected"]

    streak = 0
    cursor = end
    today_stat = day_stats.get(today_str)
    if today_stat and _has_doses(today_stat) and not _complete(today_stat):
        cursor = end - timedelta(days=1)  # grace: today not finished yet
    while cursor >= start:
        st = day_stats.get(cursor.isoformat())
        if st is None:
            break
        if not _has_doses(st):
            cursor -= timedelta(days=1)  # nothing scheduled — skip without breaking
            continue
        if _complete(st):
            streak += 1
            cursor -= timedelta(days=1)
        else:
            break

    recent = []
    rc = end - timedelta(days=6)
    while rc <= end:
        st = day_stats.get(rc.isoformat(), {"expected": 0, "taken": 0})
        pct = round(st["taken"] / st["expected"] * 100) if st["expected"] else None
        recent.append({"date": rc.isoformat(), "expected": st["expected"],
                       "taken": st["taken"], "percentage": pct})
        rc += timedelta(days=1)

    medications = []
    for sid, v in per_sched.items():
        pct = round(v["taken"] / v["expected"] * 100) if v["expected"] else None
        medications.append({
            "schedule_id": sid, "name": v["name"], "dosage": v["dosage"],
            "category": v["category"], "expected": v["expected"],
            "taken": v["taken"], "percentage": pct,
        })
    medications.sort(key=lambda m: (m["percentage"] is None, m["percentage"] or 0))

    overall_pct = round(overall_taken / overall_expected * 100) if overall_expected else None
    return {
        "days": days,
        "has_data": overall_expected > 0,
        "overall_percentage": overall_pct,
        "expected_total": overall_expected,
        "taken_total": overall_taken,
        "streak_days": streak,
        "active_medications": len(schedules),
        "medications": medications,
        "recent": recent,
    }
