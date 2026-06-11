"""
Fresh-import smoke tests for MAT / Cycle Health backend.

Covers:
- /api/health
- Demo user login (demo@cycle.app / DemoPass123!)
- Authenticated core endpoints: prediction, prediction/history, cycles,
  health-events, timeline (daily logs), water/today, meals/today, medications/today
- Full register -> DEV-mode email verification (read code from
  /var/log/supervisor/backend.err.log) -> login flow
"""
import os
import re
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://pixel-mat-dev.preview.emergentagent.com").rstrip("/")
BACKEND_LOG = "/var/log/supervisor/backend.err.log"

DEMO_EMAIL = "demo@cycle.app"
DEMO_PASSWORD = "DemoPass123!"


@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def demo_token(api):
    r = api.post(f"{BASE_URL}/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token")
    assert tok, "no access_token in login response"
    return tok


def auth_h(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---- health ----
class TestHealth:
    def test_health_ok(self, api):
        r = api.get(f"{BASE_URL}/api/health", timeout=15)
        assert r.status_code == 200
        assert r.json().get("status") == "ok"


# ---- auth ----
class TestAuth:
    def test_demo_login_returns_access_token(self, demo_token):
        # demo_token fixture asserts shape; just confirm it's a JWT-ish string
        assert isinstance(demo_token, str) and demo_token.count(".") == 2

    def test_me_with_token(self, api, demo_token):
        r = api.get(f"{BASE_URL}/api/auth/me", headers=auth_h(demo_token), timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body.get("email") == DEMO_EMAIL
        assert body.get("id")


# ---- core authenticated endpoints (fresh DB, demo has no cycles yet) ----
class TestCoreEndpoints:
    def test_prediction(self, api, demo_token):
        r = api.get(f"{BASE_URL}/api/prediction", headers=auth_h(demo_token), timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        # Cold-start: confidence should be present and numeric (0 is fine).
        assert "confidence" in body
        assert "cycleLengthPrediction" in body

    def test_prediction_history(self, api, demo_token):
        r = api.get(f"{BASE_URL}/api/prediction/history", headers=auth_h(demo_token), timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "history" in body and isinstance(body["history"], list)

    def test_cycles_list(self, api, demo_token):
        r = api.get(f"{BASE_URL}/api/cycles", headers=auth_h(demo_token), timeout=15)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_health_events_with_date_range(self, api, demo_token):
        r = api.get(
            f"{BASE_URL}/api/health-events?start_date=2026-06-01&end_date=2026-06-30",
            headers=auth_h(demo_token),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_timeline_daily_logs(self, api, demo_token):
        # The app's daily-logs equivalent is /api/timeline (returns {count, events}).
        r = api.get(f"{BASE_URL}/api/timeline", headers=auth_h(demo_token), timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "events" in body and isinstance(body["events"], list)
        assert "count" in body

    def test_water_today(self, api, demo_token):
        r = api.get(f"{BASE_URL}/api/water/today", headers=auth_h(demo_token), timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert "total_ml" in body and "goal_ml" in body

    def test_meals_today(self, api, demo_token):
        r = api.get(f"{BASE_URL}/api/meals/today", headers=auth_h(demo_token), timeout=15)
        assert r.status_code == 200
        assert "meals" in r.json()

    def test_medications_today(self, api, demo_token):
        r = api.get(f"{BASE_URL}/api/medications/today", headers=auth_h(demo_token), timeout=15)
        assert r.status_code == 200
        assert "medications" in r.json()

    def test_unauthorized_returns_401(self, api):
        r = api.get(f"{BASE_URL}/api/prediction", timeout=15)
        assert r.status_code in (401, 403)


# ---- registration -> DEV verification -> login ----
class TestRegisterVerifyLoginDevMode:
    def _read_code_for(self, email: str, attempts: int = 6) -> str:
        pat = re.compile(rf"Verification code for {re.escape(email)}:\s*(\d{{6}})", re.IGNORECASE)
        for _ in range(attempts):
            try:
                with open(BACKEND_LOG, "r") as f:
                    text = f.read()
                m = pat.findall(text)
                if m:
                    return m[-1]
            except FileNotFoundError:
                pass
            time.sleep(0.5)
        return ""

    def test_full_flow(self, api):
        email = f"TEST_smoke_{uuid.uuid4().hex[:8]}@example.com"
        password = "SmokeTest123!"

        # Register
        r = api.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": email, "password": password, "full_name": "Smoke Test"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("verification_required") is True

        # Login before verify should be blocked
        r2 = api.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
        assert r2.status_code in (401, 403), r2.text

        # Pull DEV code from backend log
        code = self._read_code_for(email)
        assert code and len(code) == 6, f"DEV verification code not found in {BACKEND_LOG} for {email}"

        # Verify-email
        r3 = api.post(
            f"{BASE_URL}/api/auth/verify-email",
            json={"email": email, "code": code},
            timeout=15,
        )
        assert r3.status_code == 200, r3.text
        assert "access_token" in r3.json()

        # Login after verify
        r4 = api.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
        assert r4.status_code == 200, r4.text
        token = r4.json().get("access_token")
        assert token

        # /api/auth/me works with new token
        r5 = api.get(f"{BASE_URL}/api/auth/me", headers=auth_h(token), timeout=15)
        assert r5.status_code == 200
        assert r5.json().get("email", "").lower() == email.lower()
