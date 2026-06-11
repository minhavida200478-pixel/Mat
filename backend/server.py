"""Menstrual health platform API — auth, cycles, logs, predictions, analytics, partner sharing."""
import logging
import secrets
import statistics
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, field_validator, model_validator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

import db
from auth import get_current_user, now_utc
import prediction_engine as prediction_engine
import prediction_engine_v2 as prediction_engine_v2
from health_events import (router as health_events_router,
                           get_water_summary, get_meal_summary)
from medications_v2 import router as medications_router
from medications_v2 import _expected_doses_on as med_expected_doses_on
from audit import router as audit_router, record_audit
from backup import router as backup_router
from rate_limit import limiter

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class LimitRequestSizeMiddleware:
    """Reject oversized request bodies (basic DoS protection) at the ASGI layer.

    Checks Content-Length and short-circuits with HTTP 413 before the body is read
    into memory. The limit is generous (5 MB) — large enough for any legitimate JSON
    payload in this app (including offline-sync writes) while blocking abuse.
    """

    def __init__(self, app: ASGIApp, max_body_size: int = 5_000_000):
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                size = int(content_length.decode())
            except ValueError:
                await Response("Invalid Content-Length", status_code=400)(scope, receive, send)
                return
            if size > self.max_body_size:
                await Response("Request body too large", status_code=413)(scope, receive, send)
                return
        await self.app(scope, receive, send)


app = FastAPI(title="Cycle Health API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(LimitRequestSizeMiddleware, max_body_size=5_000_000)

api = APIRouter(prefix="/api")


@api.get("/health")
async def health():
    """Lightweight liveness probe for monitoring/uptime checks."""
    return {"status": "ok"}

DEFAULT_FLAGS = {"periods": True, "fertility": True, "symptoms": True,
                 "moods": True, "notes": True, "hydration": True,
                 "meals": True, "medications": True, "activity": False,
                 "timeline": True, "digest": True}


# ----------------------------- Models -----------------------------
class CycleIn(BaseModel):
    start_date: str
    end_date: Optional[str] = None

    @field_validator("start_date", "end_date")
    @classmethod
    def _valid_date(cls, v):
        if v is None:
            return v
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except (ValueError, TypeError):
            raise ValueError("Date must be in YYYY-MM-DD format")
        return v

    @model_validator(mode="after")
    def _check_order(self):
        if self.start_date and self.end_date:
            if datetime.strptime(self.end_date, "%Y-%m-%d") < datetime.strptime(self.start_date, "%Y-%m-%d"):
                raise ValueError("end_date cannot be before start_date")
        return self


class CycleUpdate(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None

    @field_validator("start_date", "end_date")
    @classmethod
    def _valid_date(cls, v):
        if v is None:
            return v
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except (ValueError, TypeError):
            raise ValueError("Date must be in YYYY-MM-DD format")
        return v

    @model_validator(mode="after")
    def _check_order(self):
        if self.start_date and self.end_date:
            if datetime.strptime(self.end_date, "%Y-%m-%d") < datetime.strptime(self.start_date, "%Y-%m-%d"):
                raise ValueError("end_date cannot be before start_date")
        return self


class SymptomEntry(BaseModel):
    name: str
    severity: Literal["mild", "moderate", "severe"]


class LogIn(BaseModel):
    date: str
    symptoms: List[SymptomEntry] = []
    moods: List[str] = []
    note: str = ""
    tags: List[str] = []
    visibility: str = "private"  # private | shared


class PartnerPermissions(BaseModel):
    periods: bool = True
    fertility: bool = True
    symptoms: bool = True
    moods: bool = True
    notes: bool = True
    hydration: bool = True
    meals: bool = True
    medications: bool = True
    activity: bool = False
    timeline: bool = True
    digest: bool = True


# ----------------------------- Helpers -----------------------------
def parse_d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _is_valid_date(s) -> bool:
    if not isinstance(s, str):
        return False
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except ValueError:
        return False


async def get_user_cycles(user_id: str) -> List[dict]:
    rows = await db.cycles.find(
        {"user_id": user_id, "deleted_at": None}, {"_id": 0}
    ).sort("start_date", 1).to_list(1000)
    # Defensive: skip any legacy/malformed rows so a single bad date can never
    # 500 prediction/analytics/partner-view read paths.
    valid: List[dict] = []
    for r in rows:
        if not _is_valid_date(r.get("start_date")):
            continue
        if r.get("end_date") and not _is_valid_date(r["end_date"]):
            r["end_date"] = None
        valid.append(r)
    return valid


def compute_prediction(cycle_rows: List[dict]) -> dict:
    """Period prediction: average last 6 cycles, discard outliers (<21 or >45 days)."""
    if not cycle_rows:
        return {"has_data": False, "avg_cycle_length": 28, "avg_period_length": 5}

    sorted_rows = sorted(cycle_rows, key=lambda r: r["start_date"])
    starts = [parse_d(r["start_date"]) for r in sorted_rows]

    # cycle lengths between consecutive starts
    lengths = [(starts[i + 1] - starts[i]).days for i in range(len(starts) - 1)]
    recent = lengths[-6:]
    valid = [l for l in recent if 21 <= l <= 45]
    avg_cycle = round(statistics.mean(valid)) if valid else (
        round(statistics.mean(recent)) if recent else 28)

    # period lengths
    plens = []
    for r in sorted_rows:
        if r.get("end_date"):
            d = (parse_d(r["end_date"]) - parse_d(r["start_date"])).days + 1
            if 1 <= d <= 14:
                plens.append(d)
    avg_period = round(statistics.mean(plens)) if plens else 5

    last_start = starts[-1]
    today = date.today()
    next_period = last_start + timedelta(days=avg_cycle)
    cycle_day = (today - last_start).days + 1

    ovulation = next_period - timedelta(days=14)
    fertile_start = ovulation - timedelta(days=5)
    fertile_end = ovulation + timedelta(days=1)
    days_until = (next_period - today).days

    # Prediction confidence: higher when cycles are regular and history is longer.
    # Deliberately capped at 95% to avoid projecting false certainty.
    confidence = None
    if valid:
        n = len(valid)
        if n == 1:
            confidence = 60
        else:
            sd = statistics.pstdev(valid)
            base = 95 - sd * 7 + min(n, 6) * 1.5
            confidence = int(max(40, min(95, round(base))))
    elif recent:
        confidence = 50

    return {
        "has_data": True,
        "avg_cycle_length": avg_cycle,
        "avg_period_length": avg_period,
        "last_period_start": last_start.isoformat(),
        "cycle_day": cycle_day,
        "next_period_date": next_period.isoformat(),
        "days_until_next_period": days_until,
        "ovulation_date": ovulation.isoformat(),
        "fertile_window_start": fertile_start.isoformat(),
        "fertile_window_end": fertile_end.isoformat(),
        "total_cycles_tracked": len(sorted_rows),
        "confidence": confidence,
    }


# ----------------------------- Cycle routes -----------------------------
@api.post("/cycles")
async def create_cycle(payload: CycleIn, current=Depends(get_current_user)):
    # Prevent duplicate periods on the same start date for one user.
    existing = await db.cycles.find_one({
        "user_id": current["_id"], "start_date": payload.start_date,
        "deleted_at": None,
    })
    if existing:
        raise HTTPException(status_code=409,
                            detail="A period with this start date already exists")
    doc = {
        "_id": str(uuid.uuid4()),
        "user_id": current["_id"],
        "start_date": payload.start_date,
        "end_date": payload.end_date,
        "created_at": now_utc(),
        "updated_at": now_utc(),
        "deleted_at": None,
    }
    await db.cycles.insert_one(doc)
    await record_audit(current["_id"], "created", "cycle", doc["_id"],
                       f"Logged period starting {payload.start_date}")
    return {"id": doc["_id"], "start_date": doc["start_date"], "end_date": doc["end_date"]}


@api.get("/cycles")
async def list_cycles(current=Depends(get_current_user)):
    rows = await db.cycles.find(
        {"user_id": current["_id"], "deleted_at": None}
    ).sort("start_date", -1).to_list(1000)
    return [{"id": r["_id"], "start_date": r["start_date"],
             "end_date": r.get("end_date")} for r in rows]


@api.put("/cycles/{cycle_id}")
async def update_cycle(cycle_id: str, payload: CycleUpdate, current=Depends(get_current_user)):
    update = {k: v for k, v in payload.dict().items() if v is not None}
    update["updated_at"] = now_utc()
    res = await db.cycles.update_one(
        {"_id": cycle_id, "user_id": current["_id"]}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Cycle not found")
    return {"detail": "updated"}


@api.delete("/cycles/{cycle_id}")
async def delete_cycle(cycle_id: str, current=Depends(get_current_user)):
    res = await db.cycles.update_one(
        {"_id": cycle_id, "user_id": current["_id"]},
        {"$set": {"deleted_at": now_utc(), "updated_at": now_utc()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Cycle not found")
    await record_audit(current["_id"], "deleted", "cycle", cycle_id, "Deleted a logged period")
    return {"detail": "deleted"}


# ----------------------------- Daily log routes -----------------------------
@api.post("/logs")
async def upsert_log(payload: LogIn, current=Depends(get_current_user)):
    doc = {
        "user_id": current["_id"],
        "date": payload.date,
        "symptoms": [s.dict() for s in payload.symptoms],
        "moods": payload.moods,
        "note": payload.note,
        "tags": payload.tags,
        "visibility": payload.visibility,
        "updated_at": now_utc(),
    }
    await db.daily_logs.update_one(
        {"user_id": current["_id"], "date": payload.date},
        {"$set": doc, "$setOnInsert": {"created_at": now_utc()}},
        upsert=True)
    sym = len(payload.symptoms)
    mood = len(payload.moods)
    await record_audit(current["_id"], "updated", "daily_log", payload.date,
                       f"Saved log for {payload.date} ({sym} symptom(s), {mood} mood(s))")
    return {"detail": "saved", "date": payload.date}


@api.get("/logs")
async def list_logs(current=Depends(get_current_user)):
    rows = await db.daily_logs.find(
        {"user_id": current["_id"]}, {"_id": 0, "user_id": 0}
    ).sort("date", -1).to_list(2000)
    for r in rows:
        if isinstance(r.get("updated_at"), datetime):
            r["updated_at"] = r["updated_at"].isoformat()
        if isinstance(r.get("created_at"), datetime):
            r["created_at"] = r["created_at"].isoformat()
    return rows


@api.get("/logs/{log_date}")
async def get_log(log_date: str, current=Depends(get_current_user)):
    row = await db.daily_logs.find_one(
        {"user_id": current["_id"], "date": log_date}, {"_id": 0, "user_id": 0})
    if not row:
        return {"date": log_date, "symptoms": [], "moods": [], "note": "",
                "tags": [], "visibility": "private"}
    if isinstance(row.get("updated_at"), datetime):
        row["updated_at"] = row["updated_at"].isoformat()
    if isinstance(row.get("created_at"), datetime):
        row["created_at"] = row["created_at"].isoformat()
    return row


# ----------------------------- Dashboard & analytics -----------------------------
@api.get("/dashboard")
async def dashboard(today: Optional[str] = None, current=Depends(get_current_user)):
    cycle_rows = await get_user_cycles(current["_id"])
    prediction = compute_prediction(cycle_rows)
    # Use the client's local calendar date so the "today" log matches the date the
    # mobile app filed it under (avoids UTC-vs-device timezone day drift).
    today_str = today or date.today().isoformat()
    today_log = await db.daily_logs.find_one(
        {"user_id": current["_id"], "date": today_str},
        {"_id": 0, "user_id": 0})
    if today_log:
        for k in ("updated_at", "created_at"):
            if isinstance(today_log.get(k), datetime):
                today_log[k] = today_log[k].isoformat()
    return {"prediction": prediction, "today_log": today_log,
            "user": {"full_name": current.get("full_name")}}


@api.get("/analytics")
async def analytics(current=Depends(get_current_user)):
    cycle_rows = await get_user_cycles(current["_id"])
    sorted_rows = sorted(cycle_rows, key=lambda r: r["start_date"])
    starts = [parse_d(r["start_date"]) for r in sorted_rows]
    lengths = [(starts[i + 1] - starts[i]).days for i in range(len(starts) - 1)]
    valid = [l for l in lengths if 21 <= l <= 45]

    avg_cycle = round(statistics.mean(valid), 1) if valid else None
    period_lens = []
    for r in sorted_rows:
        if r.get("end_date"):
            d = (parse_d(r["end_date"]) - parse_d(r["start_date"])).days + 1
            if 1 <= d <= 14:
                period_lens.append(d)
    avg_period = round(statistics.mean(period_lens), 1) if period_lens else None

    # regularity score: lower stdev -> higher regularity (0-100)
    regularity = None
    if len(valid) >= 2:
        sd = statistics.pstdev(valid)
        regularity = max(0, min(100, round(100 - sd * 12)))
    elif len(valid) == 1:
        regularity = 100

    logs = await db.daily_logs.find({"user_id": current["_id"]},
                                    {"_id": 0, "symptoms": 1, "moods": 1}).to_list(2000)
    symptom_freq: dict = {}
    mood_freq: dict = {}
    for lg in logs:
        for s in lg.get("symptoms", []):
            symptom_freq[s["name"]] = symptom_freq.get(s["name"], 0) + 1
        for m in lg.get("moods", []):
            mood_freq[m] = mood_freq.get(m, 0) + 1

    return {
        "avg_cycle_length": avg_cycle,
        "avg_period_length": avg_period,
        "regularity_score": regularity,
        "cycles_tracked": len(sorted_rows),
        "cycle_lengths": lengths[-12:],
        "cycle_history": [
            {"date": sorted_rows[i]["start_date"], "length": lengths[i]}
            for i in range(len(lengths))
        ][-12:],
        "symptom_frequency": [{"name": k, "count": v}
                              for k, v in sorted(symptom_freq.items(), key=lambda x: -x[1])],
        "mood_frequency": [{"name": k, "count": v}
                           for k, v in sorted(mood_freq.items(), key=lambda x: -x[1])],
    }


# ----------------------------- Advanced prediction engine -----------------------------
@api.get("/prediction")
async def prediction(today: Optional[str] = None, current=Depends(get_current_user)):
    """Medical-grade period prediction (MAT engine).

    Returns a prediction window (never a bare date), per-day probability
    distribution, confidence score, cycle classification, trend insights and
    informational health flags — computed by a pure, deterministic statistical
    engine (no external AI). Also caches the derived UserCycleProfile.
    """
    cycle_rows = await get_user_cycles(current["_id"])
    today_date = None
    if today:
        try:
            today_date = parse_d(today)
        except ValueError:
            today_date = None

    result = prediction_engine_v2.predict(cycle_rows, today=today_date,
                                          generated_at=now_utc().isoformat())

    # Cache the derived profile (UserCycleProfile) — updated on every call so it
    # always reflects the latest cycle history.
    try:
        await db.cycle_profiles.update_one(
            {"user_id": current["_id"]},
            {"$set": {**result["profile"],
                      "user_id": current["_id"],
                      "updated_at": now_utc()},
             "$setOnInsert": {"created_at": now_utc()}},
            upsert=True,
        )
    except Exception:  # noqa: BLE001 — caching must never break the prediction read
        logger.exception("Failed to cache cycle profile for %s", current["_id"])

    # Persist a longitudinal benchmark trail (P2). Computed-only engine + a thin
    # persistence layer here: one accumulating history row per distinct (and
    # deterministic) prediction_id, plus the latest validation-metrics snapshot.
    # Wrapped so persistence can never break the prediction read.
    try:
        audit = result.get("auditTrail", {})
        pred_id = audit.get("prediction_id")
        last_cycle_start = max((c["start_date"] for c in cycle_rows), default=None)
        if pred_id:
            await db.prediction_history.update_one(
                {"user_id": current["_id"], "prediction_id": pred_id},
                {"$set": {
                    "user_id": current["_id"],
                    "prediction_id": pred_id,
                    "engine_version": result.get("engineVersion"),
                    "algorithm_version": result.get("algorithmVersion"),
                    "predicted_period_start": result.get("predictedDate"),
                    "earliest_date": result.get("earliestDate"),
                    "latest_date": result.get("latestDate"),
                    "cycle_length_prediction": result.get("cycleLengthPrediction"),
                    "confidence": result.get("confidence"),
                    "confidence_source": result.get("confidenceSource"),
                    "reliability_score": result.get("reliabilityIndex", {}).get("score"),
                    "reliability_classification":
                        result.get("reliabilityIndex", {}).get("classification"),
                    "data_sufficiency_level": result.get("dataSufficiency", {}).get("level"),
                    "model_weights": result.get("modelWeights"),
                    "last_cycle_start": last_cycle_start,
                    "updated_at": now_utc(),
                },
                 "$setOnInsert": {"generated_at": now_utc(),
                                  "prediction_date": now_utc().date().isoformat(),
                                  "actual_period_start": None,
                                  "prediction_error_days": None}},
                upsert=True,
            )

        # P2: resolve earlier stored predictions once the actual period arrives.
        # A row predicted the first period AFTER its last_cycle_start — resolve it
        # with the earliest known cycle start strictly later than that.
        sorted_starts = sorted(c["start_date"] for c in cycle_rows if c.get("start_date"))
        unresolved = await db.prediction_history.find(
            {"user_id": current["_id"], "actual_period_start": None,
             "predicted_period_start": {"$ne": None},
             "last_cycle_start": {"$ne": None},
             **({"prediction_id": {"$ne": pred_id}} if pred_id else {})},
            {"_id": 1, "last_cycle_start": 1, "predicted_period_start": 1},
        ).to_list(length=200)
        for row in unresolved:
            actual = next((s for s in sorted_starts if s > row["last_cycle_start"]), None)
            if actual is None:
                continue
            err_days = (datetime.strptime(actual, "%Y-%m-%d").date().toordinal()
                        - datetime.strptime(row["predicted_period_start"], "%Y-%m-%d")
                        .date().toordinal())
            await db.prediction_history.update_one(
                {"_id": row["_id"]},
                {"$set": {"actual_period_start": actual,
                          "prediction_error_days": err_days,
                          "resolved_at": now_utc()}},
            )

        await db.validation_metrics.update_one(
            {"user_id": current["_id"]},
            {"$set": {
                "user_id": current["_id"],
                "engine_version": result.get("engineVersion"),
                "metrics": result.get("validationMetrics"),
                "benchmark_accuracy": result.get("benchmark", {}).get("overall_accuracy"),
                "prediction_errors": result.get("predictionErrors"),
                "updated_at": now_utc(),
            },
             "$setOnInsert": {"created_at": now_utc()}},
            upsert=True,
        )

        # P11: monthly validation snapshots — one row per (user, calendar month),
        # refreshed on every prediction so the month always holds its latest state.
        month_key = now_utc().strftime("%Y-%m")
        await db.validation_snapshots.update_one(
            {"user_id": current["_id"], "month": month_key},
            {"$set": {
                "user_id": current["_id"],
                "month": month_key,
                "engine_version": result.get("engineVersion"),
                "metrics": result.get("validationMetrics"),
                "benchmark_accuracy": result.get("benchmark", {}).get("overall_accuracy"),
                "regularity": result.get("regularity"),
                "cycle_count": result.get("profile", {}).get("cycle_count"),
                "updated_at": now_utc(),
            },
             "$setOnInsert": {"created_at": now_utc()}},
            upsert=True,
        )

        # P14: persisted benchmark/validation table — one row per walk-forward
        # (predicted, actual) pair. Idempotent upsert keyed by actual start date.
        for rec in result.get("benchmark", {}).get("records", []):
            await db.benchmark_records.update_one(
                {"user_id": current["_id"],
                 "actual_period_start": rec["actual_period_start"]},
                {"$set": {
                    "user_id": current["_id"],
                    "prediction_date": rec["predicted_period_start"],
                    "predicted_period_start": rec["predicted_period_start"],
                    "actual_period_start": rec["actual_period_start"],
                    "error_days": rec["prediction_error_days"],
                    "confidence": result.get("confidence"),
                    "engine_version": result.get("engineVersion"),
                    "regularity": result.get("regularity"),
                    "cycle_count": result.get("profile", {}).get("cycle_count"),
                    "updated_at": now_utc(),
                }},
                upsert=True,
            )
    except Exception:  # noqa: BLE001 — persistence must never break the prediction read
        logger.exception("Failed to persist prediction trail for %s", current["_id"])

    return result


@api.get("/prediction/history")
async def prediction_history(limit: int = 50, current=Depends(get_current_user)):
    """Longitudinal benchmark trail: recent stored predictions + latest metrics (P2).

    Returns the most-recent ``limit`` prediction-history rows (newest first) plus
    the latest validation-metrics snapshot for the current user.
    """
    limit = max(1, min(limit, 200))
    rows = await db.prediction_history.find(
        {"user_id": current["_id"]},
        {"_id": 0},
    ).sort("updated_at", -1).to_list(length=limit)
    metrics = await db.validation_metrics.find_one(
        {"user_id": current["_id"]}, {"_id": 0},
    )
    snapshots = await db.validation_snapshots.find(
        {"user_id": current["_id"]}, {"_id": 0},
    ).sort("month", -1).to_list(length=12)
    for r in rows:
        for k in ("updated_at", "generated_at", "resolved_at"):
            if isinstance(r.get(k), datetime):
                r[k] = r[k].isoformat()
    if metrics:
        for k in ("updated_at", "created_at"):
            if isinstance(metrics.get(k), datetime):
                metrics[k] = metrics[k].isoformat()
    for s in snapshots:
        for k in ("updated_at", "created_at"):
            if isinstance(s.get(k), datetime):
                s[k] = s[k].isoformat()
    return {"history": rows, "count": len(rows), "validationMetrics": metrics,
            "monthlySnapshots": snapshots}


# ----------------------------- Symptom pattern analysis -----------------------------
_DAY_RANGES = [(1, 5), (6, 10), (11, 14), (15, 18), (19, 24), (25, 40)]
_PHASES = ["menstrual", "follicular", "ovulation", "luteal"]
_PHASE_PHRASE = {
    "menstrual": "during your period",
    "follicular": "in your follicular phase",
    "ovulation": "around ovulation",
    "luteal": "in your luteal phase (after ovulation)",
}


def _cycle_phase(cycle_day: int, avg_cycle: int, avg_period: int) -> str:
    ovu = max(10, avg_cycle - 14)
    if cycle_day <= avg_period:
        return "menstrual"
    if cycle_day < ovu - 1:
        return "follicular"
    if cycle_day <= ovu + 1:
        return "ovulation"
    return "luteal"


def _range_label(cycle_day: int) -> Optional[str]:
    for lo, hi in _DAY_RANGES:
        if lo <= cycle_day <= hi:
            return f"{lo}\u2013{hi}"
    return None


async def _compute_symptom_patterns(user_id: str) -> dict:
    """Statistical correlation of symptoms (and moods) with cycle phase / cycle day.

    Maps each logged symptom to the cycle day of the cycle it falls in, then reports
    the dominant phase, peak cycle-day range, and premenstrual recurrence rate.
    """
    cycle_rows = await get_user_cycles(user_id)
    sorted_rows = sorted(cycle_rows, key=lambda r: r["start_date"])
    starts = [parse_d(r["start_date"]) for r in sorted_rows]
    prediction = compute_prediction(cycle_rows)
    avg_cycle = int(prediction.get("avg_cycle_length") or 28)
    avg_period = int(prediction.get("avg_period_length") or 5)

    logs = await db.daily_logs.find(
        {"user_id": user_id},
        {"_id": 0, "date": 1, "symptoms": 1, "moods": 1}).to_list(3000)

    def find_cycle(d: date) -> Optional[int]:
        idx = None
        for i, s in enumerate(starts):
            if s <= d:
                idx = i
            else:
                break
        return idx

    sym_phase = defaultdict(lambda: {p: 0 for p in _PHASES})
    sym_range = defaultdict(lambda: defaultdict(int))
    sym_total = defaultdict(int)
    sym_premenstrual_cycles = defaultdict(set)
    sym_cycles = defaultdict(set)          # all cycles a symptom appeared in
    sym_days_before = defaultdict(list)    # lead time (days before next period) per occurrence
    mood_phase = defaultdict(lambda: {p: 0 for p in _PHASES})
    mood_total = defaultdict(int)
    logged_cycles = set()
    total_symptom_logs = 0

    predicted_next = None
    if prediction.get("next_period_date"):
        try:
            predicted_next = parse_d(prediction["next_period_date"])
        except Exception:
            predicted_next = None

    for lg in logs:
        try:
            d = parse_d(lg["date"])
        except Exception:
            continue
        syms = lg.get("symptoms", []) or []
        moods = lg.get("moods", []) or []
        if not syms and not moods:
            continue
        ci = find_cycle(d)
        if ci is None:
            continue
        cd = (d - starts[ci]).days + 1
        if cd < 1 or cd > 45:
            continue
        phase = _cycle_phase(cd, avg_cycle, avg_period)
        rng = _range_label(cd)
        # Lead time to the *next* period start (real next cycle, else prediction).
        if ci + 1 < len(starts):
            next_start = starts[ci + 1]
        elif predicted_next is not None:
            next_start = predicted_next
        else:
            next_start = starts[ci] + timedelta(days=avg_cycle)
        days_before = (next_start - d).days
        is_premenstrual = 0 <= days_before <= 5
        if syms:
            logged_cycles.add(ci)
        for s in syms:
            name = s.get("name")
            if not name:
                continue
            total_symptom_logs += 1
            sym_total[name] += 1
            sym_phase[name][phase] += 1
            sym_cycles[name].add(ci)
            if rng:
                sym_range[name][rng] += 1
            if 0 <= days_before <= 12:
                sym_days_before[name].append(days_before)
            if is_premenstrual:
                sym_premenstrual_cycles[name].add(ci)
        for m in moods:
            mood_total[m] += 1
            mood_phase[m][phase] += 1

    cycles_tracked = len(sorted_rows)
    denom_cycles = max(1, len(logged_cycles))
    has_enough = cycles_tracked >= 2 and total_symptom_logs >= 3 and len(sym_total) >= 1

    symptoms_out = []
    for name, total in sorted(sym_total.items(), key=lambda x: -x[1]):
        phases = sym_phase[name]
        dominant = max(phases, key=phases.get)
        dom_pct = round(phases[dominant] / total * 100)
        ranges = sym_range[name]
        peak_range = max(ranges, key=ranges.get) if ranges else None
        peak_pct = round(ranges[peak_range] / total * 100) if peak_range else 0
        premen_rate = round(len(sym_premenstrual_cycles[name]) / denom_cycles * 100)
        recurrence_rate = round(len(sym_cycles[name]) / denom_cycles * 100)

        dbs = sorted(sym_days_before[name])
        typical_days_before = dbs[len(dbs) // 2] if dbs else None  # median lead time

        # Premenstrual lead-time insight takes priority (the headline users want):
        # e.g. "Headaches appeared about 2 days before your period in 75% of cycles."
        if premen_rate >= 50 and typical_days_before is not None:
            if typical_days_before == 0:
                lead = "on the day your period started"
            elif typical_days_before == 1:
                lead = "about 1 day before your period"
            else:
                lead = f"about {typical_days_before} days before your period"
            insight = f"{name} appeared {lead} in {premen_rate}% of tracked cycles."
        else:
            insight = f"Most {name} entries fall {_PHASE_PHRASE[dominant]} ({dom_pct}%)"
            if peak_range:
                insight += f", peaking on cycle days {peak_range}"
            insight += "."

        # confident: enough samples and either a clear phase or a clear premenstrual pattern
        confident = total >= 3 and (dom_pct >= 45 or premen_rate >= 50)
        symptoms_out.append({
            "name": name,
            "total_count": total,
            "by_phase": phases,
            "dominant_phase": dominant,
            "dominant_phase_pct": dom_pct,
            "peak_day_range": peak_range,
            "peak_day_pct": peak_pct,
            "premenstrual_cycle_rate": premen_rate,
            "cycle_recurrence_rate": recurrence_rate,
            "typical_days_before": typical_days_before,
            "insight": insight,
            "confident": confident,
        })

    # Surface premenstrual lead-time insights first in the headline list.
    symptoms_out.sort(
        key=lambda s: (
            0 if (s["premenstrual_cycle_rate"] >= 50 and s["typical_days_before"] is not None) else 1,
            -s["premenstrual_cycle_rate"],
            -s["total_count"],
        )
    )

    moods_out = []
    for name, total in sorted(mood_total.items(), key=lambda x: -x[1])[:6]:
        phases = mood_phase[name]
        dominant = max(phases, key=phases.get)
        dom_pct = round(phases[dominant] / total * 100)
        moods_out.append({
            "name": name,
            "total_count": total,
            "by_phase": phases,
            "dominant_phase": dominant,
            "dominant_phase_pct": dom_pct,
        })

    headline = [s["insight"] for s in symptoms_out if s["confident"]][:5]

    return {
        "has_enough_data": has_enough,
        "cycles_tracked": cycles_tracked,
        "total_symptom_logs": total_symptom_logs,
        "avg_cycle_length": avg_cycle,
        "avg_period_length": avg_period,
        "symptoms": symptoms_out,
        "moods": moods_out,
        "insights": headline,
    }


@api.get("/symptom-patterns")
async def symptom_patterns(current=Depends(get_current_user)):
    return await _compute_symptom_patterns(current["_id"])


_SEVERITY_VALUE = {"mild": 1, "moderate": 2, "severe": 3}


@api.get("/symptom-intelligence")
async def symptom_intelligence(current=Depends(get_current_user)):
    """Deeper, statistical (non-AI) symptom intelligence built on top of the
    cycle-phase engine:
      - forecasts: forward-looking heads-up dates for premenstrual symptoms
      - correlations: symptom<->symptom and symptom<->mood co-occurrence
      - severity_trends: whether a symptom is getting worse / better over time
    """
    cycle_rows = await get_user_cycles(current["_id"])
    sorted_rows = sorted(cycle_rows, key=lambda r: r["start_date"])
    starts = [parse_d(r["start_date"]) for r in sorted_rows]
    prediction = compute_prediction(cycle_rows)
    avg_cycle = int(prediction.get("avg_cycle_length") or 28)

    predicted_next = None
    if prediction.get("next_period_date"):
        try:
            predicted_next = parse_d(prediction["next_period_date"])
        except Exception:
            predicted_next = None

    logs = await db.daily_logs.find(
        {"user_id": current["_id"]},
        {"_id": 0, "date": 1, "symptoms": 1, "moods": 1}).to_list(3000)

    parsed = []
    for lg in logs:
        try:
            parsed.append((parse_d(lg["date"]), lg))
        except Exception:
            continue
    parsed.sort(key=lambda x: x[0])

    def find_cycle(d: date) -> Optional[int]:
        idx = None
        for i, s in enumerate(starts):
            if s <= d:
                idx = i
            else:
                break
        return idx

    sym_total = defaultdict(int)
    sym_day_count = defaultdict(int)
    sym_days_before = defaultdict(list)
    sym_premen_cycles = defaultdict(set)
    sym_sev_series = defaultdict(list)
    pair_co = defaultdict(int)
    sym_mood_co = defaultdict(int)
    logged_cycles = set()
    total_symptom_logs = 0

    for d, lg in parsed:
        syms = lg.get("symptoms", []) or []
        moods = lg.get("moods", []) or []
        names = [s.get("name") for s in syms if s.get("name")]
        uniq_names = list(dict.fromkeys(names))
        uniq_moods = list(dict.fromkeys(moods))
        ci = find_cycle(d)
        next_start = None
        if ci is not None:
            if ci + 1 < len(starts):
                next_start = starts[ci + 1]
            elif predicted_next is not None:
                next_start = predicted_next
            else:
                next_start = starts[ci] + timedelta(days=avg_cycle)
            if names:
                logged_cycles.add(ci)
        for s in syms:
            name = s.get("name")
            if not name:
                continue
            total_symptom_logs += 1
            sym_total[name] += 1
            sev = _SEVERITY_VALUE.get(str(s.get("severity") or "").lower())
            if sev:
                sym_sev_series[name].append(sev)
            if ci is not None and next_start is not None:
                days_before = (next_start - d).days
                if 0 <= days_before <= 12:
                    sym_days_before[name].append(days_before)
                if 0 <= days_before <= 7:
                    sym_premen_cycles[name].add(ci)
        for nm in uniq_names:
            sym_day_count[nm] += 1
        for i in range(len(uniq_names)):
            for j in range(i + 1, len(uniq_names)):
                a, b = sorted([uniq_names[i], uniq_names[j]])
                pair_co[(a, b)] += 1
        for nm in uniq_names:
            for m in uniq_moods:
                sym_mood_co[(nm, m)] += 1

    cycles_tracked = len(sorted_rows)
    denom_cycles = max(1, len(logged_cycles))
    today = date.today()

    # ---- Forecasts (forward-looking) ----
    forecasts = []
    for name, total in sym_total.items():
        if total < 3:
            continue
        premen_rate = round(len(sym_premen_cycles[name]) / denom_cycles * 100)
        dbs = sorted(sym_days_before[name])
        typical = dbs[len(dbs) // 2] if dbs else None
        if predicted_next is not None and premen_rate >= 50 and typical is not None:
            expected = predicted_next - timedelta(days=typical)
            if expected < today - timedelta(days=1):
                continue  # already passed this cycle
            forecasts.append({
                "symptom": name,
                "expected_date": expected.isoformat(),
                "days_until": (expected - today).days,
                "days_before_period": typical,
                "confidence_pct": premen_rate,
            })
    forecasts.sort(key=lambda f: (-f["confidence_pct"], f["expected_date"]))

    # ---- Correlations (co-occurrence) ----
    correlations = []
    for (a, b), co in pair_co.items():
        base = min(sym_day_count[a], sym_day_count[b])
        if base < 2 or co < 2:
            continue
        rate = round(co / base * 100)
        if rate >= 40:
            correlations.append({
                "type": "symptom-symptom", "a": a, "b": b, "co_count": co, "rate": rate,
                "insight": f"{a} and {b} often occur together ({rate}% of the time).",
            })
    for (nm, m), co in sym_mood_co.items():
        base = sym_day_count[nm]
        if base < 3 or co < 2:
            continue
        rate = round(co / base * 100)
        if rate >= 40:
            correlations.append({
                "type": "symptom-mood", "a": nm, "b": m, "co_count": co, "rate": rate,
                "insight": f"On days with {nm}, you often feel {m} ({rate}%).",
            })
    correlations.sort(key=lambda c: -c["rate"])
    correlations = correlations[:8]

    # ---- Severity trends ----
    severity_trends = []
    for name, series in sym_sev_series.items():
        if len(series) < 4:
            continue
        half = len(series) // 2
        earlier = series[:half]
        recent = series[half:]
        ea = statistics.mean(earlier)
        ra = statistics.mean(recent)
        diff = ra - ea
        trend = "rising" if diff >= 0.4 else ("falling" if diff <= -0.4 else "stable")
        severity_trends.append({
            "symptom": name,
            "avg_severity": round(statistics.mean(series), 2),
            "recent_avg": round(ra, 2),
            "earlier_avg": round(ea, 2),
            "trend": trend,
            "samples": len(series),
            "insight": (f"{name} severity is trending {trend}."
                        if trend != "stable" else f"{name} severity has stayed steady."),
        })
    severity_trends.sort(key=lambda t: (-t["avg_severity"]))
    severity_trends = severity_trends[:8]

    # ---- Headline summary ----
    summary_insights = []
    for f in forecasts[:2]:
        when = "today" if f["days_until"] <= 0 else f"in {f['days_until']} day{'s' if f['days_until'] != 1 else ''}"
        summary_insights.append(
            f"Heads up: {f['symptom']} may appear {when}, about "
            f"{f['days_before_period']}d before your predicted period "
            f"({f['confidence_pct']}% of recent cycles)."
        )
    if correlations:
        summary_insights.append(correlations[0]["insight"])
    for t in severity_trends:
        if t["trend"] == "rising":
            summary_insights.append(f"{t['symptom']} severity has been increasing recently — worth noting.")
            break

    has_enough = cycles_tracked >= 2 and total_symptom_logs >= 4

    return {
        "has_enough_data": has_enough,
        "cycles_tracked": cycles_tracked,
        "total_symptom_logs": total_symptom_logs,
        "next_period_date": prediction.get("next_period_date"),
        "forecasts": forecasts,
        "correlations": correlations,
        "severity_trends": severity_trends,
        "summary_insights": summary_insights,
    }



# ----------------------------- Widget summary (single aggregated call) -----------------------------
async def compute_streak(user_id: str, today_str: str) -> int:
    """Consecutive days (ending today or yesterday) with at least one logged activity.

    Activity = any health event, daily log, or cycle start. A one-day grace is given
    for "today" so the streak isn't shown as broken before the user logs anything today.
    """
    today = parse_d(today_str)
    window_start = (today - timedelta(days=180)).isoformat()

    dates: set = set()
    events = await db.health_events.find(
        {"user_id": user_id, "deleted_at": None, "date": {"$gte": window_start}},
        {"_id": 0, "date": 1},
    ).to_list(5000)
    dates.update(e["date"] for e in events if e.get("date"))

    logs = await db.daily_logs.find(
        {"user_id": user_id, "date": {"$gte": window_start}}, {"_id": 0, "date": 1}
    ).to_list(5000)
    dates.update(lg["date"] for lg in logs if lg.get("date"))

    cycles = await db.cycles.find(
        {"user_id": user_id, "deleted_at": None, "start_date": {"$gte": window_start}},
        {"_id": 0, "start_date": 1},
    ).to_list(2000)
    dates.update(c["start_date"] for c in cycles if c.get("start_date"))

    streak = 0
    cur = today if today_str in dates else today - timedelta(days=1)
    while cur.isoformat() in dates:
        streak += 1
        cur = cur - timedelta(days=1)
    return streak


@api.get("/widget-summary")
async def widget_summary(today: Optional[str] = None, current=Depends(get_current_user)):
    """Everything the Android home-screen widgets need, in one request.

    Aggregates cycle prediction, hydration (+ goal-met), meals, medications, and the
    engagement streak so the (possibly headless) widget refresh makes a single call.
    """
    today_str = today or date.today().isoformat()
    cycle_rows = await get_user_cycles(current["_id"])
    prediction = compute_prediction(cycle_rows)

    water = await get_water_summary(today_str, current)
    meals = await get_meal_summary(today_str, current)
    med_count = await db.health_events.count_documents({
        "user_id": current["_id"], "event_type": "medication",
        "date": today_str, "deleted_at": None,
    })
    streak = await compute_streak(current["_id"], today_str)

    goal_ml = water.get("goal_ml", 0) or 0
    total_ml = water.get("total_ml", 0) or 0
    return {
        "prediction": prediction,
        "hydration": total_ml,
        "hydration_goal": goal_ml,
        "hydration_goal_met": goal_ml > 0 and total_ml >= goal_ml,
        "meals_logged": meals.get("completed_count", 0),
        "medications_taken": med_count,
        "streak_days": streak,
    }


# ----------------------------- Daily Summary Engine -----------------------------
@api.get("/daily-summary")
async def daily_summary(today: Optional[str] = None, current=Depends(get_current_user)):
    """A plain-language "today at a glance" summary.

    Combines cycle prediction (cycle day / phase / days until period) with the day's
    hydration, meals, medication adherence, symptoms and moods into a headline + lines.
    """
    today_str = today or date.today().isoformat()
    target = parse_d(today_str)
    cycle_rows = await get_user_cycles(current["_id"])
    prediction = compute_prediction(cycle_rows)

    water = await get_water_summary(today_str, current)
    meals = await get_meal_summary(today_str, current)

    # Symptoms / moods from the day's daily log
    log = await db.daily_logs.find_one(
        {"user_id": current["_id"], "date": today_str}, {"_id": 0})
    symptoms = (log or {}).get("symptoms", []) or []
    moods = (log or {}).get("moods", []) or []

    # Medication adherence today (planned vs taken) from schedules
    schedules = await db.med_schedules.find(
        {"user_id": current["_id"], "deleted_at": None, "enabled": True}).to_list(200)
    cache: dict = {}
    meds_planned = 0
    for sched in schedules:
        created = sched.get("created_at")
        if isinstance(created, datetime) and created.date() > target:
            continue
        times = await med_expected_doses_on(sched, current["_id"], target, cache)
        meds_planned += len(times)
    meds_taken = await db.health_events.count_documents({
        "user_id": current["_id"], "event_type": "medication", "date": today_str,
        "deleted_at": None, "data.schedule_id": {"$exists": True},
    })
    meds_taken = min(meds_taken, meds_planned) if meds_planned else meds_taken

    # ----- Build narrative -----
    cycle_day = prediction.get("cycle_day") if prediction.get("has_data") else None
    phase = None
    if cycle_day and cycle_day > 0:
        phase = _cycle_phase(cycle_day,
                             int(prediction.get("avg_cycle_length") or 28),
                             int(prediction.get("avg_period_length") or 5))
    du = prediction.get("days_until_next_period")

    if cycle_day and cycle_day > 0:
        headline = f"Cycle day {cycle_day}"
        if phase:
            headline += f" · {phase.capitalize()} phase"
    else:
        headline = "Today at a glance"

    period_line = None
    if du is not None:
        if du > 1:
            period_line = f"Period expected in {du} days ({prediction.get('next_period_date')})."
        elif du == 1:
            period_line = "Period expected tomorrow."
        elif du == 0:
            period_line = "Period expected today."
        else:
            period_line = f"Period is {abs(du)} day{'s' if abs(du) != 1 else ''} late."

    goal_ml = water.get("goal_ml", 0) or 0
    total_ml = water.get("total_ml", 0) or 0
    water_pct = round(total_ml / goal_ml * 100) if goal_ml else 0

    lines = []
    if period_line:
        lines.append(period_line)
    lines.append(f"Water {total_ml}ml of {goal_ml}ml ({water_pct}%).")
    lines.append(f"Meals {meals.get('completed_count', 0)} of 4 logged.")
    if meds_planned:
        lines.append(f"Medication {meds_taken} of {meds_planned} doses taken.")
    elif schedules:
        lines.append("No medication doses scheduled today.")
    if symptoms:
        names = ", ".join(s.get("name", "") for s in symptoms[:3] if s.get("name"))
        lines.append(f"{len(symptoms)} symptom{'s' if len(symptoms) != 1 else ''} logged ({names}).")
    if moods:
        lines.append(f"Mood: {', '.join(moods[:3])}.")

    return {
        "date": today_str,
        "headline": headline,
        "lines": lines,
        "cycle_day": cycle_day,
        "phase": phase,
        "days_until_next_period": du,
        "next_period_date": prediction.get("next_period_date"),
        "water": {"total_ml": total_ml, "goal_ml": goal_ml, "percentage": water_pct},
        "meals_completed": meals.get("completed_count", 0),
        "meals_goal": 4,
        "medications_taken": meds_taken,
        "medications_planned": meds_planned,
        "symptoms_logged": len(symptoms),
        "mood_entries": len(moods),
        "has_cycle_data": bool(prediction.get("has_data")),
    }


from partner_router import partner_api  # noqa: E402  (bottom import avoids circular dep)
from auth_router import auth_api  # noqa: E402  (bottom import avoids circular dep)

app.include_router(api)
app.include_router(auth_api)  # Authentication: register/login/verify/reset/refresh
app.include_router(partner_api)  # Partner sharing / companion dashboard
app.include_router(health_events_router)  # Unified Health Event System
app.include_router(medications_router)  # Smart Medication Reminders + Adherence
app.include_router(audit_router)  # Audit log
app.include_router(backup_router)  # Backup & Restore

app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Attach hardening headers to every response.

    This is a token-in-header JSON API (no cookies), so CORP is left cross-origin so
    the mobile app and RN-web client can read responses. CSP/frame-ancestors are locked
    down because API responses should never be embedded or render active content.
    """
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'")
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
    return response


@app.on_event("startup")
async def startup():
    await db.ensure_indexes()
    # Backfill: pre-existing accounts (created before email verification existed)
    # are treated as verified so they keep working. Only new registrations are
    # created with email_verified=False.
    await db.users.update_many({"email_verified": {"$exists": False}},
                               {"$set": {"email_verified": True}})
    logger.info("Indexes ensured")


@app.on_event("shutdown")
async def shutdown():
    db.client.close()
