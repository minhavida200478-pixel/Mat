"""JWT authentication: argon2 hashing, access/refresh tokens with rotation,
reuse detection, and FastAPI dependencies."""
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash

import db

logger = logging.getLogger(__name__)


def _load_jwt_secret() -> str:
    """Source the JWT signing secret WITHOUT a hardcoded default.

    Order: (1) JWT_SECRET env var. (2) a high-entropy secret persisted to a
    gitignored file so dev/preview stays bootable and stable across restarts and
    worker processes. (3) an ephemeral process secret if the filesystem is
    read-only (fail-safe — never a known weak default). Production should always
    set JWT_SECRET explicitly via the environment.
    """
    env_secret = os.environ.get("JWT_SECRET", "").strip()
    if env_secret:
        return env_secret
    secret_path = Path(__file__).parent / ".jwt_secret"
    try:
        if secret_path.exists():
            existing = secret_path.read_text().strip()
            if existing:
                return existing
        generated = secrets.token_urlsafe(64)
        secret_path.write_text(generated)
        try:
            os.chmod(secret_path, 0o600)
        except OSError:
            pass
        logger.warning("JWT_SECRET not set; generated a persisted secret at %s. "
                       "Set JWT_SECRET explicitly in production.", secret_path)
        return generated
    except OSError:
        logger.error("Could not persist JWT secret; using an ephemeral process secret.")
        return secrets.token_urlsafe(64)


JWT_SECRET = _load_jwt_secret()
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 30

pwd_hasher = PasswordHash.recommended()
security_scheme = HTTPBearer(auto_error=True)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    return pwd_hasher.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_hasher.verify(plain, hashed)
    except Exception:
        return False


def _create_token(subject: str, token_type: str, expires_delta: timedelta,
                  jti: Optional[str] = None) -> str:
    if jti is None:
        jti = str(uuid.uuid4())
    payload = {
        "sub": subject,
        "typ": token_type,
        "exp": now_utc() + expires_delta,
        "iat": now_utc(),
        "jti": jti,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_access_token(user_id: str) -> str:
    return _create_token(user_id, "access", timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))


def create_refresh_token(user_id: str, jti: Optional[str] = None) -> str:
    return _create_token(user_id, "refresh", timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS), jti=jti)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


async def persist_refresh_token(user_id: str, jti: str) -> None:
    await db.refresh_tokens.insert_one({
        "jti": jti,
        "user_id": user_id,
        "expires_at": now_utc() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        "used": False,
        "revoked": False,
        "created_at": now_utc(),
        "updated_at": now_utc(),
    })


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security_scheme)]
) -> dict:
    payload = decode_token(credentials.credentials)
    if payload is None or payload.get("typ") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Could not validate credentials")
    user = await db.users.find_one({"_id": payload["sub"]}, {"password_hash": 0})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
