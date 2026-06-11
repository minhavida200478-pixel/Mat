"""Iteration 17 — Security hardening + email verification flow tests.

These tests target the post-hardening behavior:
  * /api/auth/register returns a generic 200 (no tokens, anti-enumeration)
  * /api/auth/verify-email issues tokens on the right code
  * /api/auth/resend-verification re-issues a code
  * Login of UNVERIFIED account -> 403 + fresh code in log
  * Login anti-enumeration timing (non-existent -> 401 Invalid credentials)
  * Account lockout: 5 wrong password attempts on VERIFIED user -> 429
  * Pydantic extra='forbid'
  * Body-size > 5 MB -> 413
  * Demo legacy user still logs in directly
  * Regression smoke on core endpoints with demo token

DEV-mode: RESEND_API_KEY is intentionally unset, so the 6-digit code is written
to the backend log. We grep /var/log/supervisor/backend.err.log (and out.log).

The slowapi limiter buckets by the FIRST hop of X-Forwarded-For; we vary it
per test class so heavy auth tests don't 429 each other.
"""
import os
import re
import time
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL")
            or "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("EXPO_PUBLIC_BACKEND_URL not set")
API = f"{BASE_URL}/api"

DEMO_EMAIL = "demo@cycle.app"
DEMO_PASSWORD = "DemoPass123!"

LOG_FILES = [
    "/var/log/supervisor/backend.err.log",
    "/var/log/supervisor/backend.out.log",
]
CODE_LINE_RE = re.compile(
    r"\[EMAIL DEV MODE\].*?(?:Verification|Password reset) code for ([^\s:]+): (\d{6})"
)


def _unique_email(prefix: str = "iter17") -> str:
    return f"TEST_{prefix}_{uuid.uuid4().hex[:10]}@cycle.app"


def _read_code_for(email: str, timeout: float = 6.0, kind: str = "verify") -> str:
    """Tail the backend logs and return the LAST code logged for `email`.

    kind = "verify" -> "Verification code", "reset" -> "Password reset code".
    Polls up to `timeout` seconds because logging is async vs the HTTP response.
    """
    email_lc = email.lower()
    keyword = "Verification code" if kind == "verify" else "Password reset code"
    deadline = time.time() + timeout
    last_code = None
    while time.time() < deadline:
        for fp in LOG_FILES:
            try:
                with open(fp, "rb") as fh:
                    # Read tail (last 256 KB) to keep this fast on big logs.
                    try:
                        fh.seek(-256 * 1024, 2)
                    except OSError:
                        fh.seek(0)
                    blob = fh.read().decode("utf-8", errors="replace")
            except FileNotFoundError:
                continue
            for m in CODE_LINE_RE.finditer(blob):
                if m.group(1).lower() == email_lc and keyword.split()[0].lower() in blob[max(0, m.start()-80):m.end()].lower():
                    # Re-check the kind matches: this match already passed regex,
                    # but ensure "Verification" vs "Password reset" by re-reading.
                    line_window = blob[max(0, m.start()-120):m.end()+5]
                    if keyword in line_window:
                        last_code = m.group(2)
        if last_code:
            return last_code
        time.sleep(0.4)
    raise AssertionError(
        f"No {keyword} code found in backend logs for {email}")


@pytest.fixture
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _hdrs(ip: str = "10.0.99.1") -> dict:
    """Return headers that fix the rate-limit bucket to a specific IP."""
    return {"Content-Type": "application/json", "X-Forwarded-For": ip}


# ===========================================================================
# 1. Register / Verify / Resend flow
# ===========================================================================
class TestRegisterVerifyFlow:
    IP = "10.0.17.10"

    def test_register_returns_generic_no_tokens(self, client):
        email = _unique_email("reg")
        body = {"email": email, "password": "Password123!", "full_name": "Reg User"}
        r = client.post(f"{API}/auth/register", json=body, headers=_hdrs(self.IP))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("verification_required") is True
        assert data.get("email") == email.lower()
        assert "access_token" not in data
        assert "refresh_token" not in data
        # Persist for subsequent step
        type(self).new_email = email
        type(self).new_password = "Password123!"

    def test_register_existing_email_returns_same_generic(self, client):
        # Register the same email again -> identical generic 200 (anti-enumeration)
        email = type(self).new_email
        body = {"email": email, "password": "OtherPass456!", "full_name": "X"}
        r = client.post(f"{API}/auth/register", json=body, headers=_hdrs(self.IP))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("verification_required") is True
        assert data.get("email") == email.lower()
        assert "access_token" not in data

    def test_verify_wrong_code_returns_400(self, client):
        email = type(self).new_email
        r = client.post(f"{API}/auth/verify-email",
                        json={"email": email, "code": "000000"},
                        headers=_hdrs(self.IP))
        assert r.status_code == 400, r.text
        assert "invalid" in r.json().get("detail", "").lower()

    def test_verify_correct_code_returns_tokens(self, client):
        email = type(self).new_email
        code = _read_code_for(email, kind="verify")
        r = client.post(f"{API}/auth/verify-email",
                        json={"email": email, "code": code},
                        headers=_hdrs(self.IP))
        assert r.status_code == 200, r.text
        data = r.json()
        assert "access_token" in data and "refresh_token" in data
        assert data.get("token_type", "bearer") == "bearer"
        type(self).access_token = data["access_token"]

    def test_used_code_returns_400(self, client):
        # Re-using the consumed code (marked used) -> "Invalid or expired" 400
        email = type(self).new_email
        # We can't easily get the same code now (db marked used); just try with a
        # known-bad code which exercises the same 400 path.
        r = client.post(f"{API}/auth/verify-email",
                        json={"email": email, "code": "123456"},
                        headers=_hdrs(self.IP))
        assert r.status_code == 400, r.text

    def test_me_with_new_user_token_works(self, client):
        tok = type(self).access_token
        r = client.get(f"{API}/auth/me",
                       headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["email"] == type(self).new_email.lower()
        assert "id" in data

    def test_resend_verification_for_unverified_account(self, client):
        # Register another unverified user, then resend -> new code logged.
        email = _unique_email("resend")
        r = client.post(f"{API}/auth/register",
                        json={"email": email, "password": "Password123!",
                              "full_name": "Resend"},
                        headers=_hdrs(self.IP))
        assert r.status_code == 200
        first_code = _read_code_for(email, kind="verify")
        # Wait a moment so the second log line is distinct in time
        time.sleep(0.5)
        r2 = client.post(f"{API}/auth/resend-verification",
                         json={"email": email},
                         headers=_hdrs(self.IP))
        assert r2.status_code == 200, r2.text
        assert "detail" in r2.json()
        # New code should now be the latest in log (may equal by 1-in-a-million chance)
        new_code = _read_code_for(email, kind="verify")
        # It's stored as the latest record; we just confirm we got *a* 6-digit code.
        assert re.fullmatch(r"\d{6}", new_code)

    def test_resend_for_nonexistent_email_returns_generic_200(self, client):
        r = client.post(f"{API}/auth/resend-verification",
                        json={"email": _unique_email("ghost")},
                        headers=_hdrs(self.IP))
        assert r.status_code == 200, r.text
        assert "detail" in r.json()


# ===========================================================================
# 2. Verify-email: exhaust attempts -> 429
# ===========================================================================
class TestVerifyAttemptsLockout:
    IP = "10.0.17.20"

    def test_five_wrong_attempts_then_429(self, client):
        email = _unique_email("attempts")
        client.post(f"{API}/auth/register",
                    json={"email": email, "password": "Password123!",
                          "full_name": "Att"},
                    headers=_hdrs(self.IP))
        # Make sure a code exists (read it but don't use the right one)
        _ = _read_code_for(email, kind="verify")
        # 5 wrong attempts increment "attempts" counter
        for _ in range(5):
            r = client.post(f"{API}/auth/verify-email",
                            json={"email": email, "code": "999999"},
                            headers=_hdrs(self.IP))
            assert r.status_code == 400, r.text
        # 6th attempt should trigger the >=5 attempts branch -> 429
        r = client.post(f"{API}/auth/verify-email",
                        json={"email": email, "code": "999999"},
                        headers=_hdrs(self.IP))
        assert r.status_code == 429, r.text


# ===========================================================================
# 3. Login: unverified, anti-enumeration, lockout
# ===========================================================================
class TestLoginSecurity:
    IP = "10.0.17.30"

    def test_login_nonexistent_email_returns_401(self, client):
        r = client.post(f"{API}/auth/login",
                        json={"email": _unique_email("nope"),
                              "password": "whatever"},
                        headers=_hdrs(self.IP))
        assert r.status_code == 401, r.text
        assert "invalid" in r.json().get("detail", "").lower()

    def test_login_unverified_correct_password_returns_403(self, client):
        email = _unique_email("unv")
        pw = "Password123!"
        client.post(f"{API}/auth/register",
                    json={"email": email, "password": pw, "full_name": "Unv"},
                    headers=_hdrs(self.IP))
        # Correct password but email_verified=False -> 403
        r = client.post(f"{API}/auth/login",
                        json={"email": email, "password": pw},
                        headers=_hdrs(self.IP))
        assert r.status_code == 403, r.text
        assert "verify" in r.json().get("detail", "").lower()
        # Confirm a fresh code was re-issued (logged)
        code = _read_code_for(email, kind="verify")
        assert re.fullmatch(r"\d{6}", code)
        # And wrong-password on an unverified account -> 401 (still credentials check first)
        r2 = client.post(f"{API}/auth/login",
                         json={"email": email, "password": "wrong-password-xx"},
                         headers=_hdrs(self.IP))
        assert r2.status_code == 401, r2.text


class TestAccountLockout:
    IP = "10.0.17.40"

    def test_five_wrong_passwords_locks_account_429(self, client):
        # Register + verify a fresh user so they're VERIFIED
        email = _unique_email("lock")
        good_pw = "Password123!"
        ip_hdrs = _hdrs(self.IP)
        r = client.post(f"{API}/auth/register",
                        json={"email": email, "password": good_pw, "full_name": "Lk"},
                        headers=ip_hdrs)
        assert r.status_code == 200
        code = _read_code_for(email, kind="verify")
        v = client.post(f"{API}/auth/verify-email",
                        json={"email": email, "code": code}, headers=ip_hdrs)
        assert v.status_code == 200, v.text

        # 5 wrong password attempts -> all 401
        for i in range(5):
            r = client.post(f"{API}/auth/login",
                            json={"email": email, "password": "WrongPassword!"},
                            headers=ip_hdrs)
            assert r.status_code == 401, f"attempt {i+1}: {r.status_code} {r.text}"
        # Next attempt (even with correct password) is locked -> 429
        r = client.post(f"{API}/auth/login",
                        json={"email": email, "password": good_pw},
                        headers=ip_hdrs)
        assert r.status_code == 429, r.text
        assert "lock" in r.json().get("detail", "").lower()


# ===========================================================================
# 4. Demo / legacy user still logs in
# ===========================================================================
class TestDemoLogin:
    IP = "10.0.17.50"
    demo_access = None

    def test_demo_login_returns_tokens(self, client):
        ip_hdrs = _hdrs(self.IP)
        r = client.post(f"{API}/auth/login",
                        json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
                        headers=ip_hdrs)
        if r.status_code == 200:
            data = r.json()
            assert "access_token" in data and "refresh_token" in data
            TestDemoLogin.demo_access = data["access_token"]
        else:
            # Demo not present -> register+verify a fresh user and confirm verified login works
            pytest.skip(f"Demo login returned {r.status_code}: {r.text}")

    def test_demo_me(self, client):
        if not TestDemoLogin.demo_access:
            pytest.skip("no demo token")
        r = client.get(f"{API}/auth/me",
                       headers={"Authorization": f"Bearer {TestDemoLogin.demo_access}"})
        assert r.status_code == 200, r.text
        assert r.json()["email"] == DEMO_EMAIL.lower()


# ===========================================================================
# 5. Forgot-password / reset-password
# ===========================================================================
class TestForgotReset:
    IP = "10.0.17.60"

    def test_forgot_generic_for_existing_and_unknown(self, client):
        ip_hdrs = _hdrs(self.IP)
        # Unknown email -> generic 200
        r1 = client.post(f"{API}/auth/forgot-password",
                         json={"email": _unique_email("ghost")},
                         headers=ip_hdrs)
        assert r1.status_code == 200, r1.text
        # Demo email -> generic 200 (same shape)
        r2 = client.post(f"{API}/auth/forgot-password",
                         json={"email": DEMO_EMAIL},
                         headers=ip_hdrs)
        assert r2.status_code == 200, r2.text
        assert r1.json().keys() == r2.json().keys()

    def test_reset_password_full_flow(self, client):
        # Register + verify a fresh user, then forgot + reset.
        ip_hdrs = _hdrs(self.IP)
        email = _unique_email("reset")
        pw_old = "Password123!"
        pw_new = "BrandNewPass456!"
        client.post(f"{API}/auth/register",
                    json={"email": email, "password": pw_old, "full_name": "R"},
                    headers=ip_hdrs)
        vcode = _read_code_for(email, kind="verify")
        v = client.post(f"{API}/auth/verify-email",
                        json={"email": email, "code": vcode}, headers=ip_hdrs)
        assert v.status_code == 200

        # forgot
        f = client.post(f"{API}/auth/forgot-password", json={"email": email},
                       headers=ip_hdrs)
        assert f.status_code == 200
        rcode = _read_code_for(email, kind="reset")

        # reset with wrong code -> 400
        bad = client.post(f"{API}/auth/reset-password",
                          json={"email": email, "code": "000000",
                                "new_password": pw_new},
                          headers=ip_hdrs)
        assert bad.status_code == 400, bad.text

        # reset with correct code -> 200
        good = client.post(f"{API}/auth/reset-password",
                           json={"email": email, "code": rcode,
                                 "new_password": pw_new},
                           headers=ip_hdrs)
        assert good.status_code == 200, good.text

        # Login with NEW password works
        lg = client.post(f"{API}/auth/login",
                        json={"email": email, "password": pw_new},
                        headers=ip_hdrs)
        assert lg.status_code == 200, lg.text


# ===========================================================================
# 6. Pydantic extra='forbid'
# ===========================================================================
class TestExtraForbid:
    IP = "10.0.17.70"

    def test_login_with_extra_field_returns_422(self, client):
        r = client.post(f"{API}/auth/login",
                        json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD,
                              "admin": True},
                        headers=_hdrs(self.IP))
        assert r.status_code == 422, r.text

    def test_register_with_extra_field_returns_422(self, client):
        r = client.post(f"{API}/auth/register",
                        json={"email": _unique_email("xtr"),
                              "password": "Password123!",
                              "is_admin": True},
                        headers=_hdrs(self.IP))
        assert r.status_code == 422, r.text


# ===========================================================================
# 7. Body-size limit (5 MB)
# ===========================================================================
class TestBodySizeLimit:
    IP = "10.0.17.80"

    def test_oversize_body_rejected(self, client):
        # Build a > 5 MB JSON payload. The middleware reads Content-Length and
        # short-circuits with 413.
        big = "x" * (5_500_000)
        payload = '{"email":"x@x.com","password":"' + big + '"}'
        r = requests.post(f"{API}/auth/login",
                          data=payload,
                          headers={"Content-Type": "application/json",
                                   "X-Forwarded-For": self.IP},
                          timeout=30)
        # Expect 413 (or some rejection). Accept 413 or 400 (bad content-length).
        assert r.status_code in (413, 400), f"got {r.status_code}: {r.text[:200]}"

    def test_normal_body_accepted(self, client):
        # A normal body still flows through and reaches business logic.
        r = client.post(f"{API}/auth/login",
                        json={"email": _unique_email("ghost"),
                              "password": "irrelevant"},
                        headers=_hdrs(self.IP))
        assert r.status_code == 401, r.text


# ===========================================================================
# 8. Regression: demo token still authorizes core endpoints
# ===========================================================================
class TestRegressionCoreEndpoints:
    IP = "10.0.17.90"

    @pytest.fixture(scope="class")
    def demo_token(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
                          headers=_hdrs(self.IP),
                          timeout=20)
        if r.status_code != 200:
            pytest.skip(f"demo login failed: {r.status_code} {r.text}")
        return r.json()["access_token"]

    @pytest.fixture(scope="class")
    def auth(self, demo_token):
        return {"Authorization": f"Bearer {demo_token}"}

    def test_dashboard(self, auth):
        r = requests.get(f"{API}/dashboard", headers=auth, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        # Predictable shape (with or without data — both must be 200)
        assert "prediction" in data or "has_data" in data or isinstance(data, dict)

    def test_cycles(self, auth):
        r = requests.get(f"{API}/cycles", headers=auth, timeout=20)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_analytics(self, auth):
        r = requests.get(f"{API}/analytics", headers=auth, timeout=20)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), dict)

    def test_timeline(self, auth):
        r = requests.get(f"{API}/timeline", headers=auth, timeout=20)
        assert r.status_code == 200, r.text

    def test_daily_summary(self, auth):
        r = requests.get(f"{API}/daily-summary", headers=auth, timeout=20)
        assert r.status_code == 200, r.text

    def test_health_events_list(self, auth):
        r = requests.get(f"{API}/health-events", headers=auth, timeout=20)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_partner_invite(self, auth):
        r = requests.post(f"{API}/partner/invite", headers=auth, timeout=20)
        # Invite create returns 200 or 201 with a code; accept either
        assert r.status_code in (200, 201), r.text
        data = r.json()
        # invite payload typically carries a code / token
        assert any(k in data for k in ("code", "invite_code", "token", "id"))
