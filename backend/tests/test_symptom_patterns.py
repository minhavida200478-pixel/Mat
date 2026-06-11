"""Tests for the new statistical Symptom Pattern Analysis endpoint.

Covers:
  * GET /api/symptom-patterns auth gating
  * Empty/insufficient data gating (no cycles, 1 cycle, <3 symptom logs)
  * Correctness for menstrual-dominant symptoms (peak 1-5)
  * Correctness for luteal/premenstrual symptoms (peak 25-40, high premen rate)
  * Demo data-rich account returns has_enough_data=true with expected shape
"""
from __future__ import annotations

import os
import time
from datetime import date, timedelta
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")
BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL") or "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("EXPO_PUBLIC_BACKEND_URL not set")
API = f"{BASE_URL}/api"

from .conftest import register_user  # type: ignore


def _auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _seed_cycle(client, headers, start: date):
    r = client.post(f"{API}/cycles", json={"start_date": start.isoformat()},
                    headers=headers, timeout=20)
    assert r.status_code in (200, 201), f"cycle: {r.status_code} {r.text}"


def _seed_log(client, headers, d: date, symptoms=None, moods=None):
    body = {
        "date": d.isoformat(),
        "symptoms": [{"name": n, "severity": "moderate"} for n in (symptoms or [])],
        "moods": moods or [],
        "visibility": "private",
    }
    r = client.post(f"{API}/logs", json=body, headers=headers, timeout=20)
    assert r.status_code in (200, 201), f"log: {r.status_code} {r.text}"


# --------------------------------------------------------------- auth gating
class TestAuth:
    def test_requires_auth(self):
        r = requests.get(f"{API}/symptom-patterns", timeout=15)
        assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"


# --------------------------------------------------------- insufficient data
class TestInsufficientData:
    def test_brand_new_account_no_data(self, client):
        u = register_user(client, "patt_empty")
        h = _auth(u["access_token"])
        r = client.get(f"{API}/symptom-patterns", headers=h, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["has_enough_data"] is False
        assert d["cycles_tracked"] == 0
        assert d["total_symptom_logs"] == 0
        assert d["symptoms"] == []
        assert d["insights"] == []

    def test_only_one_cycle_no_logs(self, client):
        u = register_user(client, "patt_1cyc")
        h = _auth(u["access_token"])
        _seed_cycle(client, h, date.today() - timedelta(days=10))
        r = client.get(f"{API}/symptom-patterns", headers=h, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d["has_enough_data"] is False
        assert d["cycles_tracked"] == 1

    def test_two_cycles_but_under_three_symptom_logs(self, client):
        u = register_user(client, "patt_few")
        h = _auth(u["access_token"])
        base = date.today() - timedelta(days=40)
        _seed_cycle(client, h, base)
        _seed_cycle(client, h, base + timedelta(days=28))
        # only 2 symptom entries (Cramps, Cramps) — below the >=3 floor
        _seed_log(client, h, base + timedelta(days=1), symptoms=["Cramps"])
        _seed_log(client, h, base + timedelta(days=2), symptoms=["Cramps"])
        r = client.get(f"{API}/symptom-patterns", headers=h, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d["has_enough_data"] is False
        assert d["cycles_tracked"] == 2
        assert d["total_symptom_logs"] == 2


# ----------------------------------------------------------- correctness
class TestCorrectness:
    def test_menstrual_dominant_symptom(self, client):
        """Cramps logged exclusively on cycle days 1-3 -> dominant=menstrual,
        peak_day_range=1-5."""
        u = register_user(client, "patt_mens")
        h = _auth(u["access_token"])
        base = date.today() - timedelta(days=60)
        _seed_cycle(client, h, base)
        _seed_cycle(client, h, base + timedelta(days=28))
        # 3 cramps on menstrual days in two cycles
        for off in (1, 2, 3):
            _seed_log(client, h, base + timedelta(days=off - 1),
                      symptoms=["Cramps"])
        for off in (1, 2):
            _seed_log(client, h, base + timedelta(days=28 + off - 1),
                      symptoms=["Cramps"])

        r = client.get(f"{API}/symptom-patterns", headers=h, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["has_enough_data"] is True
        cramps = next((s for s in d["symptoms"] if s["name"] == "Cramps"), None)
        assert cramps is not None, d
        assert cramps["dominant_phase"] == "menstrual"
        assert cramps["dominant_phase_pct"] == 100
        assert cramps["peak_day_range"] == "1\u20135"
        assert cramps["total_count"] == 5
        # premenstrual rate must NOT be flagged in insight for menstrual-dominant
        assert "before your period" not in cramps["insight"]

    def test_luteal_premenstrual_symptom(self, client):
        """Headache logged on days 25-26 of two cycles -> dominant=luteal,
        peak=25-40, high premen rate."""
        u = register_user(client, "patt_lut")
        h = _auth(u["access_token"])
        base = date.today() - timedelta(days=70)
        _seed_cycle(client, h, base)
        _seed_cycle(client, h, base + timedelta(days=28))
        for off in (25, 26):
            _seed_log(client, h, base + timedelta(days=off - 1),
                      symptoms=["Headache"])
        for off in (25, 26):
            _seed_log(client, h, base + timedelta(days=28 + off - 1),
                      symptoms=["Headache"])

        r = client.get(f"{API}/symptom-patterns", headers=h, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["has_enough_data"] is True
        h_p = next((s for s in d["symptoms"] if s["name"] == "Headache"), None)
        assert h_p is not None
        assert h_p["dominant_phase"] == "luteal"
        assert h_p["dominant_phase_pct"] == 100
        assert h_p["peak_day_range"] == "25\u201340"
        # both cycles had premenstrual headaches -> 100%
        assert h_p["premenstrual_cycle_rate"] >= 50
        assert "before your period" in h_p["insight"]
        # headline insight should include this confident pattern
        assert any("Headache" in s for s in d["insights"])


# -------------------------------------------- demo-account integration check
class TestDemoAccount:
    def _login(self, client, email, password):
        for _ in range(15):
            r = client.post(f"{API}/auth/login",
                            json={"email": email, "password": password},
                            timeout=20)
            if r.status_code == 429:
                time.sleep(6)
                continue
            return r
        return r

    def test_demo_insights_account_returns_patterns(self, client):
        r = self._login(client, "demo_insights@example.com", "password123")
        if r.status_code != 200:
            pytest.skip(f"demo account login not available: {r.status_code} {r.text[:120]}")
        tok = r.json().get("access_token")
        assert tok
        h = _auth(tok)
        rp = client.get(f"{API}/symptom-patterns", headers=h, timeout=20)
        assert rp.status_code == 200, rp.text
        d = rp.json()
        assert d["has_enough_data"] is True, d
        assert d["cycles_tracked"] >= 2
        assert isinstance(d["symptoms"], list) and len(d["symptoms"]) >= 1
        for s in d["symptoms"]:
            assert {"name", "total_count", "by_phase", "dominant_phase",
                    "dominant_phase_pct", "peak_day_range",
                    "premenstrual_cycle_rate", "insight", "confident"
                    }.issubset(s.keys())
            assert set(s["by_phase"].keys()) == {
                "menstrual", "follicular", "ovulation", "luteal"}
            assert 0 <= s["dominant_phase_pct"] <= 100
        assert isinstance(d.get("moods"), list)
        assert isinstance(d.get("insights"), list)
