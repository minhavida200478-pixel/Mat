"""Audit logging — an append-only trail of changes to a user's health data.

record_audit() is a fire-and-forget helper called from mutating endpoints; it never
raises so it can't break the primary operation. GET /api/audit-logs returns the feed.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query

import db
from auth import get_current_user, now_utc

router = APIRouter(prefix="/api")


async def record_audit(
    user_id: str,
    action: str,                 # created | updated | deleted | restored | backed_up
    entity_type: str,            # cycle | health_event | medication | backup | ...
    entity_id: Optional[str] = None,
    summary: str = "",
    actor_type: str = "user",    # user | partner | widget | system
    actor_id: Optional[str] = None,
) -> None:
    try:
        await db.audit_logs.insert_one({
            "_id": str(uuid.uuid4()),
            "user_id": user_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "summary": summary,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "created_at": now_utc(),
        })
    except Exception:
        # Auditing must never break the primary request.
        pass


@router.get("/audit-logs")
async def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    before: Optional[str] = None,            # ISO ts cursor for pagination
    entity_type: Optional[str] = None,
    current=Depends(get_current_user),
):
    query: dict = {"user_id": current["_id"]}
    if entity_type:
        query["entity_type"] = entity_type
    if before:
        query["ts"] = {"$lt": before}
    rows = await db.audit_logs.find(query, {"_id": 0, "user_id": 0, "created_at": 0}) \
        .sort("ts", -1).limit(limit).to_list(limit)
    return {
        "items": rows,
        "next_before": rows[-1]["ts"] if len(rows) == limit else None,
    }
