"""Partner sharing & companion-dashboard routes (extracted from server.py).

Covers the read-only partner view plus the interactive shared space (notes,
check-ins, to-dos), support history and opt-in emergency contact mode.

Shared helpers (compute_prediction, get_user_cycles, _cycle_phase,
_compute_symptom_patterns, parse_d, _is_valid_date) and the PartnerPermissions
model / DEFAULT_FLAGS live in server.py and are imported here. server.py includes
partner_api at the bottom of its module, which avoids a circular import (all the
imported names are defined before that point).
"""
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

import db
from auth import get_current_user, now_utc
from health_events import get_meal_summary, get_water_summary
from server import (
    DEFAULT_FLAGS,
    PartnerPermissions,
    _compute_symptom_patterns,
    _cycle_phase,
    _is_valid_date,
    compute_prediction,
    get_user_cycles,
    parse_d,
)

partner_api = APIRouter(prefix="/api")


# ----------------------------- Partner sharing -----------------------------
@partner_api.post("/partner/invite")
async def partner_invite(current=Depends(get_current_user)):
    token = secrets.token_urlsafe(6).upper()[:8]
    doc = {
        "_id": str(uuid.uuid4()),
        "owner_id": current["_id"],
        "partner_id": None,
        "token": token,
        "status": "pending",
        "expires_at": now_utc() + timedelta(hours=48),
        "sharing_flags": DEFAULT_FLAGS.copy(),
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    await db.partner_links.insert_one(doc)
    return {"id": doc["_id"], "token": token,
            "expires_at": doc["expires_at"].isoformat()}


@partner_api.post("/partner/accept")
async def partner_accept(token: str = Body(..., embed=True), current=Depends(get_current_user)):
    link = await db.partner_links.find_one({"token": token.upper(), "status": "pending"})
    if not link:
        raise HTTPException(status_code=404, detail="Invalid or expired invite code")
    if link["expires_at"].replace(tzinfo=timezone.utc) < now_utc():
        raise HTTPException(status_code=400, detail="Invite code has expired")
    if link["owner_id"] == current["_id"]:
        raise HTTPException(status_code=400, detail="You cannot link to yourself")
    await db.partner_links.update_one(
        {"_id": link["_id"]},
        {"$set": {"partner_id": current["_id"], "status": "active", "updated_at": now_utc()}})
    owner = await db.users.find_one({"_id": link["owner_id"]}, {"password_hash": 0})
    return {"detail": "linked", "owner_name": owner.get("full_name") or owner["email"]}


@partner_api.get("/partner/links")
async def partner_links_list(current=Depends(get_current_user)):
    sharing = await db.partner_links.find(
        {"owner_id": current["_id"]}).sort("created_at", -1).to_list(100)
    sharing_out = []
    for l in sharing:
        partner = None
        if l.get("partner_id"):
            p = await db.users.find_one({"_id": l["partner_id"]}, {"password_hash": 0})
            partner = (p.get("full_name") or p["email"]) if p else None
        sharing_out.append({
            "id": l["_id"], "token": l["token"], "status": l["status"],
            "partner_name": partner, "sharing_flags": l["sharing_flags"],
            "emergency_contact": bool(l.get("emergency_contact")),
            "expires_at": l["expires_at"].isoformat(),
        })
    viewing = await db.partner_links.find(
        {"partner_id": current["_id"], "status": "active"}).to_list(100)
    viewing_out = []
    for l in viewing:
        owner = await db.users.find_one({"_id": l["owner_id"]}, {"password_hash": 0})
        viewing_out.append({
            "id": l["_id"],
            "owner_name": (owner.get("full_name") or owner["email"]) if owner else "Partner",
        })
    return {"sharing": sharing_out, "viewing": viewing_out}


@partner_api.put("/partner/links/{link_id}/permissions")
async def partner_permissions(link_id: str, perms: PartnerPermissions,
                              current=Depends(get_current_user)):
    res = await db.partner_links.update_one(
        {"_id": link_id, "owner_id": current["_id"]},
        {"$set": {"sharing_flags": perms.dict(), "updated_at": now_utc()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Link not found")
    return {"detail": "updated", "sharing_flags": perms.dict()}


@partner_api.delete("/partner/links/{link_id}")
async def partner_revoke(link_id: str, current=Depends(get_current_user)):
    res = await db.partner_links.delete_one(
        {"_id": link_id,
         "$or": [{"owner_id": current["_id"]}, {"partner_id": current["_id"]}]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Link not found")
    return {"detail": "revoked"}


@partner_api.get("/partner/view/{link_id}")
async def partner_view(link_id: str, current=Depends(get_current_user)):
    link = await db.partner_links.find_one(
        {"_id": link_id, "partner_id": current["_id"], "status": "active"})
    if not link:
        raise HTTPException(status_code=404, detail="No shared data available")
    flags = link["sharing_flags"]
    owner_id = link["owner_id"]
    owner = await db.users.find_one({"_id": owner_id}, {"password_hash": 0})
    cycle_rows = await get_user_cycles(owner_id)
    prediction = compute_prediction(cycle_rows)
    today = date.today()
    today_str = today.isoformat()
    first_name = "Your partner"
    if owner:
        first_name = (owner.get("full_name") or owner.get("email") or "Your partner").split(" ")[0]

    def _in_window(target, start, end):
        return bool(start and end and start <= target <= end)

    fertile_active = _in_window(
        today_str, prediction.get("fertile_window_start"), prediction.get("fertile_window_end"))
    period_active = False
    if prediction.get("has_data") and prediction.get("next_period_date"):
        _ap = int(prediction.get("avg_period_length") or 5)
        _pend = (parse_d(prediction["next_period_date"]) + timedelta(days=_ap - 1)).isoformat()
        period_active = _in_window(today_str, prediction["next_period_date"], _pend)
        if not period_active and prediction.get("last_period_start"):
            _lpe = (parse_d(prediction["last_period_start"]) + timedelta(days=_ap - 1)).isoformat()
            period_active = _in_window(today_str, prediction["last_period_start"], _lpe)

    shared_logs = None
    today_log = None

    out = {
        "owner_name": (owner.get("full_name") or owner["email"]) if owner else "Partner",
        "flags": flags,
        "prediction": None,
        "last_updated": None,
        "calendar": None,
        "cycle_awareness": None,
        "symptom_trends": None,
        "weekly_summary": None,
        "emergency_contact": False,
        "alerts": [],
        "care_suggestions": [],
        "logs": [],
        "hydration": None,
        "meals": None,
        "medications": None,
        "intimacy": None,
        "timeline": None,
        "digest": None,
    }

    # Most-recent activity timestamp across the owner's data (for "Updated X ago").
    _cands = []
    _he = await db.health_events.find(
        {"user_id": owner_id, "deleted_at": None}, {"_id": 0, "timestamp": 1}
    ).sort("timestamp", -1).to_list(1)
    if _he and _he[0].get("timestamp"):
        _cands.append(_he[0]["timestamp"])
    for _coll in (db.daily_logs, db.cycles):
        _r = await _coll.find(
            {"user_id": owner_id}, {"_id": 0, "updated_at": 1}
        ).sort("updated_at", -1).to_list(1)
        if _r and _r[0].get("updated_at"):
            _v = _r[0]["updated_at"]
            _cands.append(_v.isoformat() if isinstance(_v, datetime) else str(_v))
    out["last_updated"] = max(_cands) if _cands else None
    if flags.get("periods") or flags.get("fertility"):
        pred = dict(prediction)
        if not flags.get("periods"):
            for k in ["next_period_date", "days_until_next_period", "cycle_day",
                      "last_period_start"]:
                pred.pop(k, None)
        else:
            pred["period_active"] = period_active
        if not flags.get("fertility"):
            for k in ["ovulation_date", "fertile_window_start", "fertile_window_end"]:
                pred.pop(k, None)
        else:
            pred["fertile_active"] = fertile_active
        out["prediction"] = pred

    if flags.get("symptoms") or flags.get("moods") or flags.get("notes"):
        shared_logs = await db.daily_logs.find(
            {"user_id": owner_id, "visibility": "shared"},
            {"_id": 0, "user_id": 0}).sort("date", -1).to_list(120)
        for lg in shared_logs:
            if lg["date"] == today_str:
                today_log = lg
            entry = {"date": lg["date"]}
            if flags.get("symptoms"):
                entry["symptoms"] = lg.get("symptoms", [])
            if flags.get("moods"):
                entry["moods"] = lg.get("moods", [])
            if flags.get("notes"):
                entry["note"] = lg.get("note", "")
                entry["tags"] = lg.get("tags", [])
            out["logs"].append(entry)

    owner_ctx = {"_id": owner_id}

    # ---- Shared calendar (period / predicted / fertile / note / symptom days) ----
    if flags.get("periods") or flags.get("fertility") or flags.get("notes") or flags.get("symptoms"):
        period_days, predicted_period_days, fertile_days = [], [], []
        ovulation_day, note_days, symptom_days = None, [], []
        if flags.get("periods"):
            for r in cycle_rows:
                s = r.get("start_date")
                e = r.get("end_date") or s
                if not _is_valid_date(s):
                    continue
                sd = parse_d(s)
                ed = parse_d(e) if _is_valid_date(e) else sd
                if ed < sd:
                    ed = sd
                dd, guard = sd, 0
                while dd <= ed and guard < 15:
                    period_days.append(dd.isoformat())
                    dd += timedelta(days=1)
                    guard += 1
            if prediction.get("has_data") and prediction.get("next_period_date"):
                npd = parse_d(prediction["next_period_date"])
                for i in range(int(prediction.get("avg_period_length") or 5)):
                    predicted_period_days.append((npd + timedelta(days=i)).isoformat())
        if flags.get("fertility") and prediction.get("has_data"):
            fs, fe = prediction.get("fertile_window_start"), prediction.get("fertile_window_end")
            if fs and fe:
                dd, end_d = parse_d(fs), parse_d(fe)
                while dd <= end_d:
                    fertile_days.append(dd.isoformat())
                    dd += timedelta(days=1)
            ovulation_day = prediction.get("ovulation_date")
        if shared_logs:
            for lg in shared_logs:
                if flags.get("notes") and (lg.get("note") or "").strip():
                    note_days.append(lg["date"])
                if flags.get("symptoms") and (lg.get("symptoms") or []):
                    symptom_days.append(lg["date"])
        out["calendar"] = {
            "period_days": period_days,
            "predicted_period_days": predicted_period_days,
            "fertile_days": fertile_days,
            "ovulation_day": ovulation_day,
            "note_days": note_days,
            "symptom_days": symptom_days,
        }

    if flags.get("hydration"):
        w = await get_water_summary(today_str, owner_ctx)
        out["hydration"] = {
            "total_ml": w.get("total_ml", 0),
            "goal_ml": w.get("goal_ml", 0),
            "percentage": w.get("percentage", 0),
        }

    if flags.get("meals"):
        m = await get_meal_summary(today_str, owner_ctx)
        out["meals"] = {"completed_count": m.get("completed_count", 0)}

    if flags.get("medications"):
        meds = await db.health_events.find(
            {"user_id": link["owner_id"], "event_type": "medication",
             "date": today_str, "deleted_at": None}).sort("timestamp", 1).to_list(50)
        out["medications"] = {
            "count": len(meds),
            "items": [{"name": (e.get("data") or {}).get("name", "Medication"),
                       "dosage": (e.get("data") or {}).get("dosage", ""),
                       "time": e.get("timestamp", "")} for e in meds],
        }

    if flags.get("activity"):
        cnt = await db.health_events.count_documents(
            {"user_id": link["owner_id"], "event_type": "sexual_activity",
             "deleted_at": None})
        last = await db.health_events.find(
            {"user_id": link["owner_id"], "event_type": "sexual_activity",
             "deleted_at": None}).sort("timestamp", -1).to_list(1)
        out["intimacy"] = {
            "count": cnt,
            "last_date": last[0]["date"] if last else None,
        }

    if flags.get("timeline"):
        allowed = []
        if flags.get("hydration"):
            allowed.append("water")
        if flags.get("meals"):
            allowed.append("meal")
        if flags.get("medications"):
            allowed.append("medication")
        if flags.get("activity"):
            allowed.append("sexual_activity")
        timeline = []
        cutoff = (today - timedelta(days=45)).isoformat()
        if allowed:
            evs = await db.health_events.find(
                {"user_id": owner_id, "event_type": {"$in": allowed},
                 "deleted_at": None, "date": {"$gte": cutoff}}).sort("timestamp", -1).to_list(200)
            for e in evs:
                d = e.get("data") or {}
                t = e["event_type"]
                if t == "water":
                    summary = f"Water +{d.get('amount_ml', 0)} ml"
                elif t == "meal":
                    summary = f"{str(d.get('meal_type', 'meal')).title()} logged"
                elif t == "medication":
                    summary = d.get("name", "Medication")
                    if d.get("dosage"):
                        summary += f" {d['dosage']}"
                    summary += " taken"
                elif t == "sexual_activity":
                    summary = "Intimacy logged"
                else:
                    summary = t
                timeline.append({
                    "id": e["_id"], "event_type": t, "date": e.get("date", ""),
                    "timestamp": e.get("timestamp", ""), "summary": summary,
                })
        if shared_logs and (flags.get("symptoms") or flags.get("moods")):
            for lg in shared_logs:
                dt = lg["date"]
                if dt < cutoff:
                    continue
                if flags.get("symptoms"):
                    for s in lg.get("symptoms", []) or []:
                        nm = s.get("name")
                        if not nm:
                            continue
                        sev = s.get("severity")
                        timeline.append({
                            "id": f"{dt}-sym-{nm}", "event_type": "symptom", "date": dt,
                            "timestamp": "", "summary": f"Symptom: {nm}" + (f" ({sev})" if sev else ""),
                        })
                if flags.get("moods"):
                    for m in lg.get("moods", []) or []:
                        timeline.append({
                            "id": f"{dt}-mood-{m}", "event_type": "mood", "date": dt,
                            "timestamp": "", "summary": f"Mood: {m}",
                        })
        timeline.sort(key=lambda it: it["timestamp"] or (it["date"] + "T00:00:00"), reverse=True)
        out["timeline"] = timeline[:150]

    if flags.get("digest"):
        week_start = (date.today() - timedelta(days=6)).isoformat()
        ev7 = await db.health_events.find(
            {"user_id": link["owner_id"], "deleted_at": None,
             "date": {"$gte": week_start}},
            {"_id": 0, "event_type": 1, "date": 1, "data": 1}).to_list(2000)
        logs7 = await db.daily_logs.find(
            {"user_id": link["owner_id"], "date": {"$gte": week_start}},
            {"_id": 0, "symptoms": 1, "moods": 1}).to_list(100)

        headline = None
        if prediction.get("has_data") and flags.get("periods"):
            cd = prediction.get("cycle_day")
            phase = (_cycle_phase(cd, int(prediction.get("avg_cycle_length") or 28),
                                  int(prediction.get("avg_period_length") or 5))
                     if cd else None)
            if phase == "menstrual":
                phase_clause = f"{first_name} is on her period"
            elif phase:
                phase_clause = f"{first_name} is in the {phase} phase"
            else:
                phase_clause = f"{first_name}'s week at a glance"
            du = prediction.get("days_until_next_period")
            period_clause = ""
            if du is not None:
                if du > 1:
                    period_clause = f"period expected in {du} days"
                elif du == 1:
                    period_clause = "period expected tomorrow"
                elif du == 0:
                    period_clause = "period expected today"
                else:
                    period_clause = f"period is {abs(du)} day{'s' if abs(du) != 1 else ''} late"
            headline = phase_clause + (f" \u2014 {period_clause}." if period_clause else ".")

        lines = []
        if flags.get("hydration"):
            goal = (owner.get("water_goal_ml", 2000) if owner else 2000) or 2000
            total_ml = sum((e.get("data") or {}).get("amount_ml", 0)
                           for e in ev7 if e["event_type"] == "water")
            if total_ml > 0:
                avg_pct = round(total_ml / (goal * 7) * 100) if goal > 0 else 0
                if avg_pct >= 70:
                    lines.append(f"Hydration on track this week (avg {avg_pct}% of goal).")
                else:
                    lines.append(f"Hydration a little low this week (avg {avg_pct}% of goal).")
        if flags.get("symptoms"):
            scount: dict = {}
            for lg in logs7:
                for s in lg.get("symptoms", []) or []:
                    n = s.get("name")
                    if n:
                        scount[n] = scount.get(n, 0) + 1
            total_s = sum(scount.values())
            if total_s:
                top = max(scount, key=scount.get)
                lines.append(
                    f"Logged {total_s} symptom{'s' if total_s != 1 else ''} this week, "
                    f"most often {top.lower()}.")
        if flags.get("meals"):
            meal_days = len({e["date"] for e in ev7 if e["event_type"] == "meal"})
            if meal_days:
                lines.append(f"Logged meals on {meal_days} of the last 7 days.")
        if flags.get("medications"):
            med_count = sum(1 for e in ev7 if e["event_type"] == "medication")
            if med_count:
                lines.append(
                    f"Took medications {med_count} time{'s' if med_count != 1 else ''} this week.")
        if flags.get("moods"):
            mcount: dict = {}
            for lg in logs7:
                for m in lg.get("moods", []) or []:
                    mcount[m] = mcount.get(m, 0) + 1
            if mcount:
                top_mood = max(mcount, key=mcount.get)
                lines.append(f"Most frequent mood: {top_mood.lower()}.")

        if headline or lines:
            out["digest"] = {
                "headline": headline or f"{first_name}'s week at a glance",
                "lines": lines,
                "week_start": week_start,
                "week_end": date.today().isoformat(),
            }

    # ---- Cycle awareness (educational phase explainer) ----
    if (flags.get("periods") or flags.get("fertility")) and prediction.get("has_data") and prediction.get("cycle_day"):
        cd = prediction["cycle_day"]
        phase = _cycle_phase(
            cd, int(prediction.get("avg_cycle_length") or 28),
            int(prediction.get("avg_period_length") or 5))
        phase_titles = {
            "menstrual": "Menstrual phase", "follicular": "Follicular phase",
            "ovulation": "Ovulation", "luteal": "Luteal phase",
        }
        phase_desc = {
            "menstrual": "The period is happening now. Energy may be lower — rest and warmth help.",
            "follicular": "After the period. Energy typically rises through this phase.",
            "ovulation": "Around ovulation — the most fertile point of the cycle.",
            "luteal": "After ovulation, before the next period. PMS-type symptoms can show up later here.",
        }
        awareness = {
            "cycle_day": cd,
            "phase": phase,
            "phase_title": phase_titles.get(phase, "Cycle"),
            "description": phase_desc.get(phase, ""),
            "period_window": None,
        }
        if flags.get("periods"):
            du = prediction.get("days_until_next_period")
            if du is not None:
                if du < 0:
                    awareness["period_window"] = f"Period is {abs(du)} day{'s' if abs(du) != 1 else ''} late"
                elif du == 0:
                    awareness["period_window"] = "Period likely today"
                elif du == 1:
                    awareness["period_window"] = "Period likely within 1–2 days"
                else:
                    awareness["period_window"] = f"Period likely within {du - 1}–{du + 1} days"
        out["cycle_awareness"] = awareness

    # ---- Symptom trends (educational, gated by symptoms) ----
    if flags.get("symptoms"):
        sp = await _compute_symptom_patterns(owner_id)
        if sp.get("has_enough_data"):
            trends = []
            for s in sp.get("symptoms", [])[:4]:
                name = s.get("name")
                rec = s.get("cycle_recurrence_rate")
                premen = s.get("premenstrual_cycle_rate")
                tdb = s.get("typical_days_before")
                if not name:
                    continue
                if premen and premen >= 50 and tdb is not None:
                    trends.append(f"{name} tends to appear before the period ({premen}% of cycles).")
                elif rec:
                    trends.append(f"{name} occurs in {rec}% of tracked cycles.")
            if trends:
                out["symptom_trends"] = {
                    "lines": trends[:4],
                    "cycles_tracked": sp.get("cycles_tracked", 0),
                }

    # ---- Weekly summary (Tier 5 — shared health metrics) ----
    week_ago = (today - timedelta(days=6)).isoformat()
    summary = {}
    if flags.get("periods") and prediction.get("cycle_day"):
        summary["cycle_day"] = prediction["cycle_day"]
    if flags.get("hydration"):
        goal = (out.get("hydration") or {}).get("goal_ml") or 2000
        wevs = await db.health_events.find(
            {"user_id": owner_id, "event_type": "water", "deleted_at": None,
             "date": {"$gte": week_ago}}, {"_id": 0, "data": 1}).to_list(700)
        total7 = sum((e.get("data") or {}).get("amount_ml", 0) for e in wevs)
        summary["water_avg_pct"] = int(round(min(100, (total7 / 7 / goal) * 100))) if goal else 0
    if flags.get("medications"):
        summary["medication_entries"] = await db.health_events.count_documents(
            {"user_id": owner_id, "event_type": "medication", "deleted_at": None,
             "date": {"$gte": week_ago}})
    if shared_logs is not None:
        recent7 = [lg for lg in shared_logs if lg["date"] >= week_ago]
        if flags.get("symptoms"):
            summary["symptoms_logged"] = sum(len(lg.get("symptoms") or []) for lg in recent7)
        if flags.get("moods"):
            mood_counts: dict = {}
            for lg in recent7:
                for m in lg.get("moods") or []:
                    mood_counts[m] = mood_counts.get(m, 0) + 1
            if mood_counts:
                top = max(mood_counts, key=mood_counts.get)
                summary["mood_trend"] = f"Mostly {top}" if len(mood_counts) > 1 else top
    if summary:
        out["weekly_summary"] = summary

    # ---- Emergency contact mode (opt-in; owner-controlled) ----
    out["emergency_contact"] = bool(link.get("emergency_contact"))
    if out["emergency_contact"]:
        arows = await db.partner_alerts.find({"link_id": link_id}).sort("created_at", -1).to_list(20)
        out["alerts"] = [{"id": r["_id"], "from_name": r.get("from_name", "Partner"),
                          "message": r.get("message", ""), "created_at": _iso(r.get("created_at"))}
                         for r in arows]

    # ---- Care suggestions (informational, never medical advice) ----
    suggestions = []
    if flags.get("periods") and prediction.get("has_data"):
        du = prediction.get("days_until_next_period")
        if period_active:
            suggestions.append({"icon": "water",
                                "text": f"{first_name} is on her period — comfort and patience help."})
        elif du is not None and 0 <= du <= 3:
            when = "today" if du == 0 else ("tomorrow" if du == 1 else f"in {du} days")
            suggestions.append({"icon": "calendar",
                                "text": f"Period expected {when} — a little extra care is appreciated."})
    if flags.get("fertility") and fertile_active:
        suggestions.append({"icon": "leaf", "text": "Fertility window is active."})
    if flags.get("symptoms") and today_log:
        syms = [s.get("name") for s in (today_log.get("symptoms") or []) if s.get("name")]
        if syms:
            suggestions.append({"icon": "pulse",
                                "text": "Shared symptom today: " + ", ".join(syms[:3]) + "."})
    if flags.get("medications") and out.get("medications") and out["medications"].get("count"):
        suggestions.append({"icon": "medkit", "text": "Medication logged today."})
    if flags.get("hydration") and out.get("hydration"):
        pct = out["hydration"].get("percentage", 0)
        if 0 < pct < 60:
            suggestions.append({"icon": "water",
                                "text": f"Hydration is at {round(pct)}% today — a gentle nudge could help."})
    out["care_suggestions"] = suggestions[:5]

    return out


# ----------------------------- Partner shared space (Tier 3) -----------------------
class NoteIn(BaseModel):
    text: str


class CheckinIn(BaseModel):
    prompt: str


class CheckinRespondIn(BaseModel):
    response: str


class TodoIn(BaseModel):
    text: str


class TodoUpdate(BaseModel):
    done: bool


async def _get_link_member(link_id: str, user: dict):
    """Return (link, role, other_id) if the current user is a member of an active
    link; otherwise 404. Shared-space features work for BOTH owner and partner."""
    link = await db.partner_links.find_one(
        {"_id": link_id, "status": "active",
         "$or": [{"owner_id": user["_id"]}, {"partner_id": user["_id"]}]})
    if not link:
        raise HTTPException(status_code=404, detail="No shared space available")
    role = "owner" if link["owner_id"] == user["_id"] else "partner"
    other_id = link["partner_id"] if role == "owner" else link["owner_id"]
    return link, role, other_id


def _first_name(u: Optional[dict]) -> str:
    if not u:
        return "Someone"
    return (u.get("full_name") or u.get("email") or "Someone").split(" ")[0]


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


def _checkin_out(doc: dict, uid: str) -> dict:
    return {
        "id": doc["_id"], "link_id": doc["link_id"],
        "from_id": doc.get("from_id"), "from_name": doc.get("from_name", "Someone"),
        "prompt": doc.get("prompt", ""), "response": doc.get("response"),
        "responder_id": doc.get("responder_id"),
        "created_at": _iso(doc.get("created_at")), "responded_at": _iso(doc.get("responded_at")),
        "mine": doc.get("from_id") == uid,
        "can_respond": doc.get("response") is None and doc.get("from_id") != uid,
    }


def _todo_out(doc: dict) -> dict:
    return {
        "id": doc["_id"], "text": doc.get("text", ""), "done": bool(doc.get("done")),
        "created_by_name": doc.get("created_by_name", "Someone"),
        "created_at": _iso(doc.get("created_at")),
    }


async def _log_support(link_id: str, actor: dict, kind: str, label: str):
    """Record a positive-engagement support action (Tier 5 Support History).
    Intentionally only logs supportive actions — never surveillance/access events."""
    await db.partner_support.insert_one({
        "_id": str(uuid.uuid4()), "link_id": link_id, "actor_id": actor["_id"],
        "actor_name": _first_name(actor), "kind": kind, "label": label,
        "created_at": now_utc(),
    })


# ---- Partner notes ----
@partner_api.post("/partner/{link_id}/notes", status_code=201)
async def partner_note_create(link_id: str, payload: NoteIn, current=Depends(get_current_user)):
    await _get_link_member(link_id, current)
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Note cannot be empty")
    doc = {
        "_id": str(uuid.uuid4()), "link_id": link_id, "author_id": current["_id"],
        "author_name": _first_name(current), "text": text[:1000], "created_at": now_utc(),
    }
    await db.partner_notes.insert_one(doc)
    await _log_support(link_id, current, "note", "Supportive note sent")
    return {"id": doc["_id"], "author_name": doc["author_name"], "text": doc["text"],
            "created_at": _iso(doc["created_at"]), "mine": True}


@partner_api.get("/partner/{link_id}/notes")
async def partner_notes_list(link_id: str, current=Depends(get_current_user)):
    await _get_link_member(link_id, current)
    rows = await db.partner_notes.find({"link_id": link_id}).sort("created_at", -1).to_list(200)
    return {"notes": [{
        "id": r["_id"], "author_id": r.get("author_id"), "author_name": r.get("author_name", "Someone"),
        "text": r.get("text", ""), "created_at": _iso(r.get("created_at")),
        "mine": r.get("author_id") == current["_id"],
    } for r in rows]}


@partner_api.delete("/partner/{link_id}/notes/{note_id}")
async def partner_note_delete(link_id: str, note_id: str, current=Depends(get_current_user)):
    await _get_link_member(link_id, current)
    res = await db.partner_notes.delete_one(
        {"_id": note_id, "link_id": link_id, "author_id": current["_id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"detail": "deleted"}


# ---- Partner check-ins ----
@partner_api.post("/partner/{link_id}/checkins", status_code=201)
async def partner_checkin_create(link_id: str, payload: CheckinIn, current=Depends(get_current_user)):
    await _get_link_member(link_id, current)
    prompt = (payload.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt required")
    doc = {
        "_id": str(uuid.uuid4()), "link_id": link_id, "from_id": current["_id"],
        "from_name": _first_name(current), "prompt": prompt[:200], "response": None,
        "responder_id": None, "responded_at": None, "created_at": now_utc(),
    }
    await db.partner_checkins.insert_one(doc)
    await _log_support(link_id, current, "checkin_sent", "Check-in sent")
    return _checkin_out(doc, current["_id"])


@partner_api.post("/partner/{link_id}/checkins/{checkin_id}/respond")
async def partner_checkin_respond(link_id: str, checkin_id: str, payload: CheckinRespondIn,
                                  current=Depends(get_current_user)):
    await _get_link_member(link_id, current)
    resp = (payload.response or "").strip()
    if not resp:
        raise HTTPException(status_code=400, detail="Response required")
    upd = await db.partner_checkins.update_one(
        {"_id": checkin_id, "link_id": link_id},
        {"$set": {"response": resp[:200], "responder_id": current["_id"], "responded_at": now_utc()}})
    if upd.matched_count == 0:
        raise HTTPException(status_code=404, detail="Check-in not found")
    doc = await db.partner_checkins.find_one({"_id": checkin_id})
    await _log_support(link_id, current, "checkin_done", "Check-in completed")
    return _checkin_out(doc, current["_id"])


@partner_api.get("/partner/{link_id}/checkins")
async def partner_checkins_list(link_id: str, current=Depends(get_current_user)):
    await _get_link_member(link_id, current)
    rows = await db.partner_checkins.find({"link_id": link_id}).sort("created_at", -1).to_list(100)
    return {"checkins": [_checkin_out(r, current["_id"]) for r in rows]}


# ---- Shared to-do list ----
@partner_api.post("/partner/{link_id}/todos", status_code=201)
async def partner_todo_create(link_id: str, payload: TodoIn, current=Depends(get_current_user)):
    await _get_link_member(link_id, current)
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Item required")
    doc = {
        "_id": str(uuid.uuid4()), "link_id": link_id, "text": text[:200], "done": False,
        "created_by": current["_id"], "created_by_name": _first_name(current),
        "created_at": now_utc(), "updated_at": now_utc(),
    }
    await db.partner_todos.insert_one(doc)
    await _log_support(link_id, current, "todo", "Added a shared to-do")
    return _todo_out(doc)


@partner_api.get("/partner/{link_id}/todos")
async def partner_todos_list(link_id: str, current=Depends(get_current_user)):
    await _get_link_member(link_id, current)
    rows = await db.partner_todos.find({"link_id": link_id}).sort(
        [("done", 1), ("created_at", -1)]).to_list(200)
    return {"todos": [_todo_out(r) for r in rows]}


@partner_api.put("/partner/{link_id}/todos/{todo_id}")
async def partner_todo_update(link_id: str, todo_id: str, payload: TodoUpdate,
                              current=Depends(get_current_user)):
    await _get_link_member(link_id, current)
    res = await db.partner_todos.update_one(
        {"_id": todo_id, "link_id": link_id},
        {"$set": {"done": payload.done, "updated_at": now_utc()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"detail": "updated", "done": payload.done}


@partner_api.delete("/partner/{link_id}/todos/{todo_id}")
async def partner_todo_delete(link_id: str, todo_id: str, current=Depends(get_current_user)):
    await _get_link_member(link_id, current)
    res = await db.partner_todos.delete_one({"_id": todo_id, "link_id": link_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"detail": "deleted"}


class SupportIn(BaseModel):
    kind: str
    label: str


class EmergencyToggle(BaseModel):
    enabled: bool


class AlertIn(BaseModel):
    message: str


# ---- Support history (Tier 5 — positive engagement only) ----
@partner_api.get("/partner/{link_id}/support")
async def partner_support_list(link_id: str, current=Depends(get_current_user)):
    await _get_link_member(link_id, current)
    rows = await db.partner_support.find({"link_id": link_id}).sort("created_at", -1).to_list(100)
    return {"support": [{
        "id": r["_id"], "kind": r.get("kind"), "label": r.get("label"),
        "actor_name": r.get("actor_name", "Someone"), "created_at": _iso(r.get("created_at")),
        "mine": r.get("actor_id") == current["_id"],
    } for r in rows]}


@partner_api.post("/partner/{link_id}/support", status_code=201)
async def partner_support_create(link_id: str, payload: SupportIn, current=Depends(get_current_user)):
    await _get_link_member(link_id, current)
    label = (payload.label or "").strip()[:120] or "Support action"
    await _log_support(link_id, current, (payload.kind or "support")[:40], label)
    return {"detail": "logged"}


# ---- Emergency contact mode (opt-in; only the data owner controls it) ----
@partner_api.put("/partner/links/{link_id}/emergency")
async def partner_set_emergency(link_id: str, payload: EmergencyToggle,
                                current=Depends(get_current_user)):
    res = await db.partner_links.update_one(
        {"_id": link_id, "owner_id": current["_id"], "status": "active"},
        {"$set": {"emergency_contact": payload.enabled, "updated_at": now_utc()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Link not found")
    return {"emergency_contact": payload.enabled}


@partner_api.post("/partner/{link_id}/alerts", status_code=201)
async def partner_alert_create(link_id: str, payload: AlertIn, current=Depends(get_current_user)):
    link, role, _ = await _get_link_member(link_id, current)
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the data owner can send alerts")
    if not link.get("emergency_contact"):
        raise HTTPException(status_code=400, detail="Enable emergency contact mode first")
    msg = (payload.message or "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="Message required")
    doc = {"_id": str(uuid.uuid4()), "link_id": link_id, "from_name": _first_name(current),
           "message": msg[:300], "created_at": now_utc()}
    await db.partner_alerts.insert_one(doc)
    return {"id": doc["_id"], "from_name": doc["from_name"], "message": doc["message"],
            "created_at": _iso(doc["created_at"])}


@partner_api.get("/partner/{link_id}/alerts")
async def partner_alerts_list(link_id: str, current=Depends(get_current_user)):
    await _get_link_member(link_id, current)
    rows = await db.partner_alerts.find({"link_id": link_id}).sort("created_at", -1).to_list(50)
    return {"alerts": [{
        "id": r["_id"], "from_name": r.get("from_name", "Partner"),
        "message": r.get("message", ""), "created_at": _iso(r.get("created_at")),
    } for r in rows]}
