"""Shared pytest fixtures for cycle-health backend API tests."""
import os
import time
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

# Load frontend .env so we read the public preview URL the user actually hits.
load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL")
            or "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("EXPO_PUBLIC_BACKEND_URL / EXPO_BACKEND_URL not set")

API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture(scope="session")
def api_url() -> str:
    return API


@pytest.fixture
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _unique_email(prefix: str = "test") -> str:
    return f"TEST_{prefix}_{uuid.uuid4().hex[:10]}@cycle.app"


def _read_verification_code(email: str) -> str | None:
    """In DEV email mode the verification code is logged. Scan the backend logs for
    the most recent code issued for this email."""
    import re
    pattern = re.compile(
        r"Verification code for " + re.escape(email) + r":\s*(\d{4,8})",
        re.IGNORECASE,
    )
    code = None
    for log_path in ("/var/log/supervisor/backend.err.log",
                     "/var/log/supervisor/backend.out.log"):
        try:
            with open(log_path, "r", errors="ignore") as fh:
                for line in fh:
                    m = pattern.search(line)
                    if m:
                        code = m.group(1)  # keep the last (most recent) match
        except OSError:
            continue
    return code


def register_user(client, prefix: str = "user", password: str = "Password123",
                  full_name: str | None = None, max_wait: int = 90) -> dict:
    """Register + verify a user via the two-step email-verification flow.

    Register no longer returns tokens; it emails a code (DEV mode logs it). We read
    the code from the backend log and call /auth/verify-email to obtain tokens.
    Transparently waits out the 10/min register rate-limit (429) so large suites
    stay deterministic without weakening the live security control.
    """
    email = _unique_email(prefix)
    body = {"email": email, "password": password,
            "full_name": full_name or prefix.title()}
    deadline = time.time() + max_wait
    while True:
        r = client.post(f"{API}/auth/register", json=body, timeout=20)
        if r.status_code == 429 and time.time() < deadline:
            time.sleep(6)
            continue
        assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
        break

    # Give the (synchronous) log write a moment, then read the issued code.
    code = None
    for _ in range(10):
        code = _read_verification_code(email)
        if code:
            break
        time.sleep(0.5)
    assert code, f"verification code not found in backend log for {email}"

    vr = client.post(f"{API}/auth/verify-email",
                     json={"email": email, "code": code}, timeout=20)
    assert vr.status_code == 200, f"verify-email failed: {vr.status_code} {vr.text}"
    data = vr.json()
    return {
        "email": email,
        "password": password,
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
    }


@pytest.fixture
def fresh_user(client):
    """Register a fresh user and return tokens + meta."""
    return register_user(client, "user")


@pytest.fixture
def auth_headers(fresh_user):
    return {"Authorization": f"Bearer {fresh_user['access_token']}",
            "Content-Type": "application/json"}
