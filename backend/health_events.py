"""Unified Health Event System — powers timeline, analytics, search, and sync."""
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

import db
from audit import record_audit
from auth import get_current_user, now_utc
from models import (
    HealthEventIn, HealthEventOut, HealthEventType,
    WaterLogIn, WaterGoalIn, WaterSummary,
    MealLogIn, MealSummary, MealType,
    MedicationIn, MedicationReminderIn,
    SexualActivityIn, QuickLogIn,
    DailySummary
)

router = APIRouter(prefix="/api")


# ----------------------------- Helpers -----------------------------
def event_out(doc: dict) -> dict:
    """Convert DB document to output format."""
    out = {
        "id": doc["_id"],
        "user_id": doc["user_id"],
        "event_type": doc["event_type"],
        "timestamp": doc["timestamp"],
        "date": doc["date"],
        "data": doc.get("data", {}),
        "note": doc.get("note"),
        "visibility": doc.get("visibility", "private"),
        "tags": doc.get("tags", []),
        "created_by": doc["created_by"],
        "created_by_type": doc.get("created_by_type", "user"),
        "created_at": doc["created_at"].isoformat() if isinstance(doc["created_at"], datetime) else doc["created_at"],
        "updated_at": doc["updated_at"].isoformat() if isinstance(doc["updated_at"], datetime) else doc["updated_at"],
        "deleted_at": doc.get("deleted_at"),
    }
    return out


async def create_health_event(
    user_id: str,
    event_type: str,
    timestamp: str,
    date: str,
    data: dict = None,
    note: str = None,
    visibility: str = "private",
    tags: list = None,
    created_by: str = None,
    created_by_type: str = "user",
    client_id: str = None,
) -> dict:
    """Create a new health event (idempotent when a client_id is supplied).

    client_id lets the offline sync queue safely replay a write: if an event with the
    same (user_id, client_id) already exists, the existing one is returned instead of
    inserting a duplicate.
    """
    if client_id:
        existing = await db.health_events.find_one(
            {"user_id": user_id, "client_id": client_id})
        if existing:
            return existing
    doc = {
        "_id": str(uuid.uuid4()),
        "user_id": user_id,
        "event_type": event_type,
        "timestamp": timestamp,
        "date": date,
        "data": data or {},
        "note": note,
        "visibility": visibility,
        "tags": tags or [],
        "created_by": created_by or user_id,
        "created_by_type": created_by_type,
        "client_id": client_id,
        "created_at": now_utc(),
        "updated_at": now_utc(),
        "deleted_at": None,
    }
    try:
        await db.health_events.insert_one(doc)
    except DuplicateKeyError:
        # Concurrent replay of the same client_id raced past the find_one above.
        # The unique partial index guarantees only one survives — return it.
        existing = await db.health_events.find_one(
            {"user_id": user_id, "client_id": client_id})
        if existing:
            return existing
        raise
    return doc


# ----------------------------- Health Events CRUD -----------------------------
@router.post("/health-events")
async def create_event(payload: HealthEventIn, current=Depends(get_current_user)):
    """Create a health event."""
    doc = await create_health_event(
        user_id=current["_id"],
        event_type=payload.event_type,
        timestamp=payload.timestamp,
        date=payload.date,
        data=payload.data,
        note=payload.note,
        visibility=payload.visibility,
        tags=payload.tags,
        client_id=payload.client_id,
    )
    return event_out(doc)


@router.get("/health-events")
async def list_events(
    event_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    current=Depends(get_current_user)
):
    """List health events with optional filtering."""
    query = {"user_id": current["_id"], "deleted_at": None}
    if event_type:
        query["event_type"] = event_type
    if start_date:
        query["date"] = {"$gte": start_date}
    if end_date:
        query.setdefault("date", {})["$lte"] = end_date
    
    rows = await db.health_events.find(query).sort("timestamp", -1).to_list(limit)
    return [event_out(r) for r in rows]


@router.get("/health-events/{event_id}")
async def get_event(event_id: str, current=Depends(get_current_user)):
    """Get a single health event."""
    doc = await db.health_events.find_one({
        "_id": event_id,
        "user_id": current["_id"],
        "deleted_at": None
    })
    if not doc:
        raise HTTPException(status_code=404, detail="Event not found")
    return event_out(doc)


@router.put("/health-events/{event_id}")
async def update_event(event_id: str, payload: HealthEventIn, current=Depends(get_current_user)):
    """Update a health event."""
    update = {
        "event_type": payload.event_type,
        "timestamp": payload.timestamp,
        "date": payload.date,
        "data": payload.data,
        "note": payload.note,
        "visibility": payload.visibility,
        "tags": payload.tags,
        "updated_at": now_utc(),
    }
    res = await db.health_events.update_one(
        {"_id": event_id, "user_id": current["_id"], "deleted_at": None},
        {"$set": update}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"detail": "updated"}


@router.delete("/health-events/{event_id}")
async def delete_event(event_id: str, current=Depends(get_current_user)):
    """Soft delete a health event."""
    res = await db.health_events.update_one(
        {"_id": event_id, "user_id": current["_id"]},
        {"$set": {"deleted_at": now_utc(), "updated_at": now_utc()}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Event not found")
    await record_audit(current["_id"], "deleted", "health_event", event_id,
                       "Deleted a logged entry")
    return {"detail": "deleted"}


# ----------------------------- Quick Log -----------------------------
@router.post("/quick-log")
async def quick_log(payload: QuickLogIn, current=Depends(get_current_user)):
    """Universal quick log - creates appropriate health event."""
    ts = payload.timestamp or datetime.now(timezone.utc).isoformat()
    date = ts[:10]  # Extract YYYY-MM-DD
    
    # Map quick log action to health event
    event_data = payload.data.copy()
    
    if payload.action == "period_start":
        # Also create a cycle entry
        cycle_doc = {
            "_id": str(uuid.uuid4()),
            "user_id": current["_id"],
            "start_date": date,
            "end_date": None,
            "created_at": now_utc(),
            "updated_at": now_utc(),
            "deleted_at": None,
        }
        await db.cycles.insert_one(cycle_doc)
    
    elif payload.action == "period_end":
        # Update latest cycle with end date
        await db.cycles.update_one(
            {"user_id": current["_id"], "end_date": None},
            {"$set": {"end_date": date, "updated_at": now_utc()}},
        )
    
    elif payload.action == "water":
        event_data.setdefault("amount_ml", 250)
    
    elif payload.action == "meal":
        event_data.setdefault("meal_type", "snack")
        event_data.setdefault("status", "completed")
    
    doc = await create_health_event(
        user_id=current["_id"],
        event_type=payload.action,
        timestamp=ts,
        date=date,
        data=event_data,
        note=event_data.get("note"),
        client_id=payload.client_id,
    )
    
    return event_out(doc)


# ----------------------------- Water Tracking -----------------------------
@router.post("/water")
async def log_water(payload: WaterLogIn, current=Depends(get_current_user)):
    """Log water intake."""
    ts = payload.timestamp or datetime.now(timezone.utc).isoformat()
    date = ts[:10]
    
    doc = await create_health_event(
        user_id=current["_id"],
        event_type="water",
        timestamp=ts,
        date=date,
        data={"amount_ml": payload.amount_ml},
        note=payload.note,
        client_id=payload.client_id,
    )
    return event_out(doc)


@router.get("/water/today")
async def get_water_today(current=Depends(get_current_user)):
    """Get today's water intake summary."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return await get_water_summary(today, current)


@router.get("/water/analytics")
async def water_analytics(days: int = Query(default=7, le=30), current=Depends(get_current_user)):
    """Get water intake analytics for the last N days."""
    from datetime import timedelta
    
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days-1)
    
    user = await db.users.find_one({"_id": current["_id"]})
    goal_ml = user.get("water_goal_ml", 2000)
    
    # Get all water events in range
    logs = await db.health_events.find({
        "user_id": current["_id"],
        "event_type": "water",
        "date": {"$gte": start_date.isoformat(), "$lte": end_date.isoformat()},
        "deleted_at": None
    }).to_list(1000)
    
    # Group by date
    daily_totals = {}
    for log in logs:
        d = log["date"]
        daily_totals[d] = daily_totals.get(d, 0) + log.get("data", {}).get("amount_ml", 0)
    
    # Build response
    history = []
    current_date = start_date
    while current_date <= end_date:
        d = current_date.isoformat()
        total = daily_totals.get(d, 0)
        history.append({
            "date": d,
            "total_ml": total,
            "goal_ml": goal_ml,
            "percentage": min(100, round((total / goal_ml) * 100, 1)) if goal_ml > 0 else 0
        })
        current_date += timedelta(days=1)
    
    # Calculate averages
    totals = [h["total_ml"] for h in history]
    avg_daily = round(sum(totals) / len(totals)) if totals else 0
    days_goal_met = sum(1 for h in history if h["total_ml"] >= goal_ml)
    
    return {
        "days": days,
        "goal_ml": goal_ml,
        "avg_daily_ml": avg_daily,
        "days_goal_met": days_goal_met,
        "history": history
    }


@router.get("/water/{date}")
async def get_water_by_date(date: str, current=Depends(get_current_user)):
    """Get water intake summary for a specific date."""
    return await get_water_summary(date, current)


async def get_water_summary(date: str, current: dict) -> dict:
    """Calculate water summary for a date."""
    # Get user's water goal
    user = await db.users.find_one({"_id": current["_id"]})
    goal_ml = user.get("water_goal_ml", 2000)
    
    # Get all water events for the date
    logs = await db.health_events.find({
        "user_id": current["_id"],
        "event_type": "water",
        "date": date,
        "deleted_at": None
    }).sort("timestamp", 1).to_list(100)
    
    total_ml = sum(log.get("data", {}).get("amount_ml", 0) for log in logs)
    percentage = min(100, round((total_ml / goal_ml) * 100, 1)) if goal_ml > 0 else 0
    remaining_ml = max(0, goal_ml - total_ml)
    
    return {
        "date": date,
        "total_ml": total_ml,
        "goal_ml": goal_ml,
        "percentage": percentage,
        "remaining_ml": remaining_ml,
        "logs": [
            {
                "id": log["_id"],
                "amount_ml": log.get("data", {}).get("amount_ml", 0),
                "timestamp": log["timestamp"],
                "note": log.get("note"),
            }
            for log in logs
        ]
    }


@router.put("/water/goal")
async def set_water_goal(payload: WaterGoalIn, current=Depends(get_current_user)):
    """Set daily water goal."""
    await db.users.update_one(
        {"_id": current["_id"]},
        {"$set": {"water_goal_ml": payload.goal_ml, "updated_at": now_utc()}}
    )
    return {"detail": "goal updated", "goal_ml": payload.goal_ml}


# ----------------------------- Meal Tracking -----------------------------
@router.post("/meals")
async def log_meal(payload: MealLogIn, current=Depends(get_current_user)):
    """Log a meal."""
    ts = payload.timestamp or datetime.now(timezone.utc).isoformat()
    date = ts[:10]
    
    doc = await create_health_event(
        user_id=current["_id"],
        event_type="meal",
        timestamp=ts,
        date=date,
        data={
            "meal_type": payload.meal_type,
            "status": payload.status,
        },
        note=payload.note,
        client_id=payload.client_id,
    )
    return event_out(doc)


@router.get("/meals/today")
async def get_meals_today(current=Depends(get_current_user)):
    """Get today's meal summary."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return await get_meal_summary(today, current)


@router.get("/meals/{date}")
async def get_meals_by_date(date: str, current=Depends(get_current_user)):
    """Get meal summary for a specific date."""
    return await get_meal_summary(date, current)


async def get_meal_summary(date: str, current: dict) -> dict:
    """Calculate meal summary for a date."""
    logs = await db.health_events.find({
        "user_id": current["_id"],
        "event_type": "meal",
        "date": date,
        "deleted_at": None
    }).sort("timestamp", 1).to_list(20)
    
    meals = {
        "breakfast": None,
        "lunch": None,
        "dinner": None,
        "snack": []
    }
    
    completed = 0
    skipped = 0
    
    for log in logs:
        data = log.get("data", {})
        meal_type = data.get("meal_type", "snack")
        entry = {
            "id": log["_id"],
            "status": data.get("status", "completed"),
            "timestamp": log["timestamp"],
            "note": log.get("note"),
        }
        
        if data.get("status") == "completed":
            completed += 1
        else:
            skipped += 1
        
        if meal_type == "snack":
            meals["snack"].append(entry)
        else:
            meals[meal_type] = entry
    
    return {
        "date": date,
        "meals": meals,
        "completed_count": completed,
        "skipped_count": skipped
    }


# ----------------------------- Medication Tracking -----------------------------
@router.post("/medications")
async def log_medication(payload: MedicationIn, current=Depends(get_current_user)):
    """Log medication taken."""
    ts = payload.timestamp or datetime.now(timezone.utc).isoformat()
    date = ts[:10]
    
    doc = await create_health_event(
        user_id=current["_id"],
        event_type="medication",
        timestamp=ts,
        date=date,
        data={
            "name": payload.name,
            "dosage": payload.dosage,
            "category": payload.category,
        },
        note=payload.note,
        client_id=payload.client_id,
    )
    return event_out(doc)


@router.get("/medications/today")
async def get_medications_today(current=Depends(get_current_user)):
    """Get today's medication logs."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    logs = await db.health_events.find({
        "user_id": current["_id"],
        "event_type": "medication",
        "date": today,
        "deleted_at": None
    }).sort("timestamp", 1).to_list(50)
    
    return {
        "date": today,
        "medications": [event_out(log) for log in logs],
        "count": len(logs)
    }


@router.get("/medications/history")
async def medication_history(
    medication_name: Optional[str] = None,
    days: int = Query(default=30, le=90),
    current=Depends(get_current_user)
):
    """Get medication history."""
    from datetime import timedelta
    
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days-1)
    
    query = {
        "user_id": current["_id"],
        "event_type": "medication",
        "date": {"$gte": start_date.isoformat(), "$lte": end_date.isoformat()},
        "deleted_at": None
    }
    
    if medication_name:
        query["data.name"] = medication_name
    
    logs = await db.health_events.find(query).sort("timestamp", -1).to_list(500)
    
    return {
        "days": days,
        "total_entries": len(logs),
        "medications": [event_out(log) for log in logs]
    }


# ----------------------------- Sexual Activity Tracking -----------------------------
@router.post("/sexual-activity")
async def log_sexual_activity(payload: SexualActivityIn, current=Depends(get_current_user)):
    """Log sexual activity (privacy-first)."""
    ts = payload.timestamp or datetime.now(timezone.utc).isoformat()
    date = ts[:10]
    
    doc = await create_health_event(
        user_id=current["_id"],
        event_type="sexual_activity",
        timestamp=ts,
        date=date,
        data={
            "protection_used": payload.protection_used,
            "partner_present": payload.partner_present,
        },
        note=payload.note,
        visibility="shared" if payload.share_with_partner else "private",
        client_id=payload.client_id,
    )
    return event_out(doc)


@router.get("/sexual-activity/history")
async def sexual_activity_history(
    days: int = Query(default=30, le=90),
    current=Depends(get_current_user)
):
    """Get sexual activity history."""
    from datetime import timedelta
    
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days-1)
    
    logs = await db.health_events.find({
        "user_id": current["_id"],
        "event_type": "sexual_activity",
        "date": {"$gte": start_date.isoformat(), "$lte": end_date.isoformat()},
        "deleted_at": None
    }).sort("timestamp", -1).to_list(100)
    
    return {
        "days": days,
        "total_entries": len(logs),
        "logs": [event_out(log) for log in logs]
    }


# ----------------------------- Timeline View -----------------------------
@router.get("/timeline")
async def get_timeline(
    date: Optional[str] = None,
    event_types: Optional[str] = None,  # Comma-separated
    search: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    current=Depends(get_current_user)
):
    """Get chronological timeline of all health events."""
    query = {"user_id": current["_id"], "deleted_at": None}
    
    if date:
        query["date"] = date
    
    if event_types:
        types = [t.strip() for t in event_types.split(",")]
        query["event_type"] = {"$in": types}
    
    if search:
        safe = re.escape(search)
        query["$or"] = [
            {"note": {"$regex": safe, "$options": "i"}},
            {"data.name": {"$regex": safe, "$options": "i"}},
            {"tags": {"$regex": safe, "$options": "i"}},
        ]
    
    events = await db.health_events.find(query).sort("timestamp", -1).to_list(limit)
    
    return {
        "count": len(events),
        "events": [event_out(e) for e in events]
    }


# ----------------------------- Global Search -----------------------------
@router.get("/search")
async def global_search(
    q: str = Query(..., min_length=1),
    event_types: Optional[str] = None,
    limit: int = Query(default=50, le=100),
    current=Depends(get_current_user)
):
    """Search across all health data."""
    query = {
        "user_id": current["_id"],
        "deleted_at": None,
        "$or": [
            {"note": {"$regex": re.escape(q), "$options": "i"}},
            {"data.name": {"$regex": re.escape(q), "$options": "i"}},
            {"data.meal_type": {"$regex": re.escape(q), "$options": "i"}},
            {"tags": {"$regex": re.escape(q), "$options": "i"}},
        ]
    }
    
    if event_types:
        types = [t.strip() for t in event_types.split(",")]
        query["event_type"] = {"$in": types}
    
    results = await db.health_events.find(query).sort("timestamp", -1).to_list(limit)
    
    return {
        "query": q,
        "count": len(results),
        "results": [event_out(r) for r in results]
    }
