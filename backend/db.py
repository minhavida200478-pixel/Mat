"""MongoDB connection and collection pointers (shared across modules)."""
import os
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

# Collections
users = db.users
refresh_tokens = db.refresh_tokens
cycles = db.cycles
daily_logs = db.daily_logs
partner_links = db.partner_links
health_events = db.health_events  # Unified Health Event System
med_schedules = db.med_schedules  # Medication reminder schedules
audit_logs = db.audit_logs  # Append-only change history
backups = db.backups  # Account data snapshots
password_resets = db.password_resets  # Single-use password reset codes
email_verifications = db.email_verifications  # Single-use email verification codes
partner_notes = db.partner_notes  # Supportive notes between linked partners
partner_checkins = db.partner_checkins  # Partner check-in prompts + quick responses
partner_todos = db.partner_todos  # Shared to-do list per partner link
partner_support = db.partner_support  # Positive-engagement support history per link
partner_alerts = db.partner_alerts  # Opt-in emergency health alerts per link
cycle_profiles = db.cycle_profiles  # Cached UserCycleProfile from the prediction engine
prediction_history = db.prediction_history  # Longitudinal prediction trail (one row per prediction_id)
validation_metrics = db.validation_metrics  # Latest engine validation/benchmark snapshot per user
validation_snapshots = db.validation_snapshots  # Monthly validation snapshots (one per user+month, P11)
benchmark_records = db.benchmark_records  # Persisted walk-forward benchmark/validation table (P14)


async def ensure_indexes() -> None:
    await users.create_index("email", unique=True)
    await refresh_tokens.create_index("jti", unique=True)
    await refresh_tokens.create_index("user_id")
    await cycles.create_index([("user_id", 1), ("start_date", 1)])
    await daily_logs.create_index([("user_id", 1), ("date", 1)], unique=True)
    await partner_links.create_index("token")
    await partner_links.create_index("owner_id")
    await partner_links.create_index("partner_id")
    
    # Health Events indexes for timeline, analytics, and search
    await health_events.create_index([("user_id", 1), ("date", -1)])
    await health_events.create_index([("user_id", 1), ("event_type", 1), ("date", -1)])
    await health_events.create_index([("user_id", 1), ("timestamp", -1)])
    await health_events.create_index([("user_id", 1), ("deleted_at", 1)])
    await health_events.create_index([("user_id", 1), ("visibility", 1)])
    await health_events.create_index("created_by")  # For partner-logged events

    # Medication schedules
    await med_schedules.create_index([("user_id", 1), ("deleted_at", 1)])
    await health_events.create_index([("user_id", 1), ("data.schedule_id", 1), ("date", -1)])
    # Offline-sync idempotency: dedupe replayed writes. Unique on (user_id, client_id)
    # but only for events that actually carry a client_id (partial index), so events
    # without one (client_id=None) are unaffected.
    try:
        await health_events.drop_index("user_id_1_client_id_1")
    except Exception:
        pass  # index didn't exist yet (fresh DB) — nothing to drop
    await health_events.create_index(
        [("user_id", 1), ("client_id", 1)],
        unique=True,
        partialFilterExpression={"client_id": {"$type": "string"}},
    )
    # Audit log + backups
    await audit_logs.create_index([("user_id", 1), ("ts", -1)])
    await backups.create_index([("user_id", 1), ("created_at", -1)])
    await password_resets.create_index("email")
    await password_resets.create_index("expires_at", expireAfterSeconds=0)
    await email_verifications.create_index("email")
    await email_verifications.create_index("expires_at", expireAfterSeconds=0)
    # Partner shared space
    await partner_notes.create_index([("link_id", 1), ("created_at", -1)])
    await partner_checkins.create_index([("link_id", 1), ("created_at", -1)])
    await partner_todos.create_index([("link_id", 1), ("done", 1), ("created_at", -1)])
    await partner_support.create_index([("link_id", 1), ("created_at", -1)])
    await partner_alerts.create_index([("link_id", 1), ("created_at", -1)])
    await cycle_profiles.create_index("user_id", unique=True)
    await prediction_history.create_index([("user_id", 1), ("prediction_id", 1)], unique=True)
    await prediction_history.create_index([("user_id", 1), ("updated_at", -1)])
    await validation_metrics.create_index("user_id", unique=True)
    await validation_snapshots.create_index([("user_id", 1), ("month", -1)], unique=True)
    await benchmark_records.create_index(
        [("user_id", 1), ("actual_period_start", 1)], unique=True)
