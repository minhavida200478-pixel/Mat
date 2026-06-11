"""Pydantic models for the Cycle Health API — Unified Health Event System."""
from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, EmailStr, Field

# ----------------------------- Auth Models -----------------------------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: Optional[str] = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None


# ----------------------------- Cycle Models -----------------------------
class CycleIn(BaseModel):
    start_date: str
    end_date: Optional[str] = None


class CycleUpdate(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None


# ----------------------------- Daily Log Models -----------------------------
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


# ----------------------------- Partner Models -----------------------------
class PartnerPermissions(BaseModel):
    periods: bool = True
    fertility: bool = True
    symptoms: bool = True
    moods: bool = True
    notes: bool = True
    # New partner logging permissions
    can_log_medication: bool = False
    can_log_water: bool = False
    can_log_meals: bool = False
    can_log_symptoms: bool = False
    can_add_notes: bool = False


# ----------------------------- Unified Health Event Models -----------------------------
HealthEventType = Literal[
    "period_start", "period_end", "symptom", "mood", "medication",
    "water", "meal", "sexual_activity", "note"
]


class HealthEventBase(BaseModel):
    """Base model for all health events - supports unified timeline, search, and analytics."""
    event_type: HealthEventType
    timestamp: str  # ISO datetime
    date: str  # YYYY-MM-DD for grouping
    data: dict = {}  # Type-specific data
    note: Optional[str] = None
    visibility: str = "private"  # private | shared
    tags: List[str] = []


class HealthEventIn(HealthEventBase):
    """Input model for creating health events."""
    client_id: Optional[str] = None  # offline-sync idempotency key


class HealthEventOut(HealthEventBase):
    """Output model for health events."""
    id: str
    user_id: str
    created_by: str  # user_id or partner_id
    created_by_type: Literal["user", "partner"]  # For display "Logged by User/Partner"
    created_at: str
    updated_at: str
    deleted_at: Optional[str] = None


# ----------------------------- Water Tracking Models -----------------------------
class WaterLogIn(BaseModel):
    """Quick water log input."""
    amount_ml: int  # 250, 500, 750, 1000 etc.
    timestamp: Optional[str] = None  # ISO datetime, defaults to now
    note: Optional[str] = None
    client_id: Optional[str] = None  # offline-sync idempotency key


class WaterGoalIn(BaseModel):
    """Set daily water goal."""
    goal_ml: int = 2000  # Default 2L


class WaterSummary(BaseModel):
    """Daily water summary."""
    date: str
    total_ml: int
    goal_ml: int
    percentage: float
    remaining_ml: int
    logs: List[dict]  # List of individual logs


# ----------------------------- Meal Tracking Models -----------------------------
MealType = Literal["breakfast", "lunch", "dinner", "snack"]


class MealLogIn(BaseModel):
    """Meal log input."""
    meal_type: MealType
    status: Literal["completed", "skipped"] = "completed"
    timestamp: Optional[str] = None
    note: Optional[str] = None
    client_id: Optional[str] = None  # offline-sync idempotency key


class MealSummary(BaseModel):
    """Daily meal summary."""
    date: str
    meals: dict  # {breakfast: {...}, lunch: {...}, ...}
    completed_count: int
    skipped_count: int


# ----------------------------- Medication Tracking Models -----------------------------
class MedicationIn(BaseModel):
    """Medication log input."""
    name: str  # e.g., "Ibuprofen", "Birth Control"
    dosage: Optional[str] = None  # e.g., "400mg"
    category: Literal["painkiller", "birth_control", "vitamin", "supplement", "custom"] = "custom"
    timestamp: Optional[str] = None
    note: Optional[str] = None
    client_id: Optional[str] = None  # offline-sync idempotency key


class MedicationReminderIn(BaseModel):
    """Medication reminder settings."""
    medication_name: str
    dosage: Optional[str] = None
    schedule_type: Literal["daily", "weekly", "custom"] = "daily"
    times: List[str] = []  # List of times like ["09:00", "21:00"]
    days_of_week: List[int] = []  # 0=Mon, 6=Sun for weekly
    enabled: bool = True


# ----------------------------- Sexual Activity Models -----------------------------
class SexualActivityIn(BaseModel):
    """Sexual activity log input."""
    timestamp: Optional[str] = None
    protection_used: bool = True
    partner_present: bool = True
    note: Optional[str] = None
    # Privacy settings
    share_with_partner: bool = False
    client_id: Optional[str] = None  # offline-sync idempotency key


# ----------------------------- Quick Log Models -----------------------------
QuickLogAction = Literal[
    "period_start", "period_end", "symptom", "mood",
    "medication", "water", "meal", "sexual_activity", "note"
]


class QuickLogIn(BaseModel):
    """Universal quick log input - 3 taps or less."""
    action: QuickLogAction
    data: dict = {}  # Action-specific data
    timestamp: Optional[str] = None
    client_id: Optional[str] = None  # offline-sync idempotency key


# ----------------------------- Timeline Models -----------------------------
class TimelineFilter(BaseModel):
    """Timeline filtering options."""
    event_types: List[HealthEventType] = []
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    search_query: Optional[str] = None


# ----------------------------- Daily Summary Models -----------------------------
class DailySummary(BaseModel):
    """Daily health summary."""
    date: str
    water_progress: dict  # {consumed_ml, goal_ml, percentage}
    meals_completed: int
    medications_taken: int
    symptoms_logged: int
    mood_entries: int
    notes_created: int
    sexual_activity_logged: bool
