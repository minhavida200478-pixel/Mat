"""Authentication routes (extracted from server.py).

Covers registration + email verification, login (with lockout + timing-equalized
failure path), refresh-token rotation, logout, the /auth/me identity endpoint, and
the password-reset flow. The slowapi limiter lives in rate_limit.py so this module
and server.py can share it without a circular import.

DEFAULT_FLAGS (the default partner-sharing prefs applied to new accounts) is defined
in server.py and imported at the bottom — server.py includes auth_api only after
DEFAULT_FLAGS is defined, mirroring the partner_router pattern and avoiding a cycle.
"""
import secrets
import uuid
from datetime import timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field

import db
import email_service
from audit import record_audit
from auth import (create_access_token, create_refresh_token, decode_token,
                  get_current_user, hash_password, now_utc,
                  persist_refresh_token, verify_password)
from rate_limit import limiter
from server import DEFAULT_FLAGS  # noqa: E402  (bottom import in server avoids cycle)

auth_api = APIRouter(prefix="/api")

MAX_FAILED = 5
LOCK_MINUTES = 15
RESET_CODE_TTL_MIN = 15
MAX_RESET_ATTEMPTS = 5
VERIFY_CODE_TTL_MIN = 30
MAX_VERIFY_ATTEMPTS = 5

# Precomputed Argon2 hash of a throwaway value. Verifying against it on the
# "user not found" path makes login spend the same time as a real check, so an
# attacker can't distinguish existing vs non-existing emails by response timing.
_DUMMY_PW_HASH = hash_password("timing-equalizer-not-a-real-password-7f3a9c1e")


# ----------------------------- Models -----------------------------
class RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: Optional[str] = Field(default=None, max_length=120)


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ForgotPasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr


class ResetPasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    code: str = Field(min_length=4, max_length=12)
    new_password: str = Field(min_length=8, max_length=128)


class VerifyEmailIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    code: str = Field(min_length=4, max_length=12)


class ResendVerificationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None


# ----------------------------- Helpers -----------------------------
def user_out(doc: dict) -> dict:
    return {"id": doc["_id"], "email": doc["email"], "full_name": doc.get("full_name")}


async def _issue_verification_code(email: str) -> None:
    """Invalidate any prior codes for this email and email a fresh single-use code."""
    await db.email_verifications.delete_many({"email": email})
    code = f"{secrets.randbelow(1000000):06d}"
    await db.email_verifications.insert_one({
        "_id": str(uuid.uuid4()),
        "email": email,
        "code_hash": hash_password(code),
        "expires_at": now_utc() + timedelta(minutes=VERIFY_CODE_TTL_MIN),
        "used": False,
        "attempts": 0,
        "created_at": now_utc(),
    })
    email_service.send_verification_email(email, code, VERIFY_CODE_TTL_MIN)


# ----------------------------- Auth routes -----------------------------
@auth_api.post("/auth/register", status_code=200)
@limiter.limit("10/minute")
@limiter.limit("30/hour")
async def register(request: Request, payload: RegisterIn):
    """Create an unverified account and email a verification code.

    Returns the SAME generic response whether or not the email already exists, so the
    endpoint can't be used to enumerate registered accounts. The password is always
    hashed to keep response timing consistent across both paths. No tokens are issued
    until the email is verified via /auth/verify-email.
    """
    email = payload.email.lower()
    generic = {
        "detail": "If registration is possible, we've sent a verification code to your email.",
        "verification_required": True,
        "email": email,
    }
    # Always hash to equalize timing and avoid leaking account existence.
    pw_hash = hash_password(payload.password)

    existing = await db.users.find_one({"email": email})
    if existing:
        # Only (re)issue a code for accounts that still need verification. Verified
        # accounts are left untouched (and get no code), preventing enumeration.
        if existing.get("email_verified") is False:
            await _issue_verification_code(email)
        return generic

    await db.users.insert_one({
        "_id": str(uuid.uuid4()),
        "email": email,
        "full_name": payload.full_name,
        "password_hash": pw_hash,
        "email_verified": False,
        "sharing_prefs": DEFAULT_FLAGS.copy(),
        "failed_logins": 0,
        "lock_until": None,
        "created_at": now_utc(),
        "updated_at": now_utc(),
    })
    await _issue_verification_code(email)
    return generic


@auth_api.post("/auth/verify-email", response_model=TokenPair)
@limiter.limit("10/minute")
async def verify_email(request: Request, payload: VerifyEmailIn):
    """Confirm an email with the single-use code and sign the user in (issue tokens)."""
    email = payload.email.lower()
    invalid = HTTPException(status_code=400, detail="Invalid or expired verification code")
    rec = await db.email_verifications.find_one(
        {"email": email, "used": False}, sort=[("created_at", -1)])
    if not rec:
        raise invalid
    if rec["expires_at"].replace(tzinfo=timezone.utc) < now_utc():
        await db.email_verifications.delete_one({"_id": rec["_id"]})
        raise HTTPException(status_code=400, detail="Verification code has expired. Request a new one.")
    if rec.get("attempts", 0) >= MAX_VERIFY_ATTEMPTS:
        await db.email_verifications.delete_one({"_id": rec["_id"]})
        raise HTTPException(status_code=429, detail="Too many attempts. Request a new code.")
    if not verify_password(payload.code, rec["code_hash"]):
        await db.email_verifications.update_one({"_id": rec["_id"]}, {"$inc": {"attempts": 1}})
        raise invalid

    user = await db.users.find_one({"email": email})
    if not user:
        raise invalid

    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"email_verified": True, "failed_logins": 0,
                  "lock_until": None, "updated_at": now_utc()}})
    await db.email_verifications.update_one({"_id": rec["_id"]}, {"$set": {"used": True}})
    jti = str(uuid.uuid4())
    await persist_refresh_token(user["_id"], jti)
    return TokenPair(access_token=create_access_token(user["_id"]),
                     refresh_token=create_refresh_token(user["_id"], jti))


@auth_api.post("/auth/resend-verification")
@limiter.limit("5/minute")
async def resend_verification(request: Request, payload: ResendVerificationIn):
    """Re-send a verification code. Generic response (no account enumeration)."""
    generic = {"detail": "If your account still needs verification, a new code has been sent."}
    email = payload.email.lower()
    user = await db.users.find_one({"email": email})
    if user and user.get("email_verified") is False:
        await _issue_verification_code(email)
    return generic


@auth_api.post("/auth/login", response_model=TokenPair)
@limiter.limit("10/minute")
@limiter.limit("100/hour")
async def login(request: Request, payload: LoginIn):
    user = await db.users.find_one({"email": payload.email.lower()})
    if not user:
        # Hash a throwaway value so timing matches the real-user path.
        verify_password(payload.password, _DUMMY_PW_HASH)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    lock_until = user.get("lock_until")
    if lock_until and lock_until.replace(tzinfo=timezone.utc) > now_utc():
        raise HTTPException(status_code=429,
                            detail="Account temporarily locked due to failed attempts")

    if not verify_password(payload.password, user["password_hash"]):
        failed = user.get("failed_logins", 0) + 1
        update = {"failed_logins": failed, "updated_at": now_utc()}
        if failed >= MAX_FAILED:
            update["lock_until"] = now_utc() + timedelta(minutes=LOCK_MINUTES)
        await db.users.update_one({"_id": user["_id"]}, {"$set": update})
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Password is correct. Block sign-in until the email is verified (only newly
    # registered accounts carry email_verified=False; legacy accounts are unaffected).
    if user.get("email_verified") is False:
        await _issue_verification_code(user["email"])
        raise HTTPException(
            status_code=403,
            detail="Please verify your email to continue. We've sent a fresh code to your inbox.")

    await db.users.update_one({"_id": user["_id"]},
                              {"$set": {"failed_logins": 0, "lock_until": None}})
    jti = str(uuid.uuid4())
    await persist_refresh_token(user["_id"], jti)
    return TokenPair(access_token=create_access_token(user["_id"]),
                     refresh_token=create_refresh_token(user["_id"], jti))


@auth_api.post("/auth/refresh", response_model=TokenPair)
@limiter.limit("30/hour")
async def refresh(request: Request, refresh_token: str = Body(..., embed=True)):
    payload = decode_token(refresh_token)
    if payload is None or payload.get("typ") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    rt = await db.refresh_tokens.find_one({"jti": payload["jti"]})
    user_id = payload["sub"]
    if not rt or rt.get("revoked") or rt.get("used"):
        await db.refresh_tokens.update_many({"user_id": user_id},
                                            {"$set": {"revoked": True}})
        raise HTTPException(status_code=401, detail="Session invalidated; please log in again")

    await db.refresh_tokens.update_one({"jti": payload["jti"]},
                                       {"$set": {"used": True, "updated_at": now_utc()}})
    new_jti = str(uuid.uuid4())
    await persist_refresh_token(user_id, new_jti)
    return TokenPair(access_token=create_access_token(user_id),
                     refresh_token=create_refresh_token(user_id, new_jti))


@auth_api.post("/auth/logout")
async def logout(current=Depends(get_current_user)):
    await db.refresh_tokens.update_many({"user_id": current["_id"]},
                                        {"$set": {"revoked": True}})
    return {"detail": "Logged out"}


@auth_api.get("/auth/me", response_model=UserOut)
async def me(current=Depends(get_current_user)):
    return user_out(current)


@auth_api.post("/auth/forgot-password")
@limiter.limit("5/minute")
async def forgot_password(request: Request, payload: ForgotPasswordIn):
    """Always returns 200 (avoids email enumeration). If the account exists, emails
    a single-use, time-limited reset code."""
    generic = {"detail": "If an account exists for that email, a reset code has been sent."}
    email = payload.email.lower()
    user = await db.users.find_one({"email": email})
    if not user:
        return generic

    # Invalidate any prior outstanding codes for this email.
    await db.password_resets.delete_many({"email": email})

    code = f"{secrets.randbelow(1000000):06d}"
    await db.password_resets.insert_one({
        "_id": str(uuid.uuid4()),
        "email": email,
        "code_hash": hash_password(code),
        "expires_at": now_utc() + timedelta(minutes=RESET_CODE_TTL_MIN),
        "used": False,
        "attempts": 0,
        "created_at": now_utc(),
    })
    email_service.send_password_reset_email(email, code, RESET_CODE_TTL_MIN)
    return generic


@auth_api.post("/auth/reset-password")
@limiter.limit("10/minute")
async def reset_password(request: Request, payload: ResetPasswordIn):
    email = payload.email.lower()
    reset = await db.password_resets.find_one(
        {"email": email, "used": False}, sort=[("created_at", -1)])
    if not reset:
        raise HTTPException(status_code=400, detail="Invalid or expired reset code")

    if reset["expires_at"].replace(tzinfo=timezone.utc) < now_utc():
        await db.password_resets.delete_one({"_id": reset["_id"]})
        raise HTTPException(status_code=400, detail="Reset code has expired. Request a new one.")

    if reset.get("attempts", 0) >= MAX_RESET_ATTEMPTS:
        await db.password_resets.delete_one({"_id": reset["_id"]})
        raise HTTPException(status_code=429, detail="Too many attempts. Request a new code.")

    if not verify_password(payload.code, reset["code_hash"]):
        await db.password_resets.update_one(
            {"_id": reset["_id"]}, {"$inc": {"attempts": 1}})
        raise HTTPException(status_code=400, detail="Invalid or expired reset code")

    user = await db.users.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset code")

    # Update password, consume the code, and revoke all sessions.
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"password_hash": hash_password(payload.new_password),
                  "failed_logins": 0, "lock_until": None, "updated_at": now_utc()}})
    await db.password_resets.update_one({"_id": reset["_id"]}, {"$set": {"used": True}})
    await db.refresh_tokens.update_many({"user_id": user["_id"]}, {"$set": {"revoked": True}})
    await record_audit(user["_id"], "updated", "user", user["_id"], "Password reset via email code")
    return {"detail": "Password updated. Please sign in with your new password."}
