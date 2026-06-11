# MAT / Cycle Health — PRD

## Original Problem Statement
1. Import GitHub repo (https://github.com/minhavida200478-pixel/Mat.git) — a privacy-first
   menstrual health tracker (Expo + FastAPI + MongoDB) — and set it up for continued development.
2. Build a medical-grade period prediction engine (pure statistical, no external AI):
   weighted prediction, MAD outlier detection, confidence scoring, prediction windows,
   per-day probability distribution, cycle classification, adaptive self-correction,
   trend detection, informational health flags. <100ms, deterministic, 95%+ test coverage.

## Architecture
- Frontend: Expo Router (SDK 54), React Native 0.81, expo-router file-based routes.
- Backend: FastAPI (modular routers: auth, partner, health_events, medications_v2, audit, backup).
- DB: MongoDB (motor). Collections incl. cycles, daily_logs, health_events, cycle_profiles.
- Auth: JWT (argon2/pwdlib) + email verification (Resend; DEV mode logs codes to backend log).

## User Personas
- Primary: a person tracking their menstrual cycle for predictions & health insights.
- Secondary: a linked partner with permissioned, privacy-gated visibility.

## Core Requirements (static)
- Cycle/period CRUD, daily logs, dashboard, analytics, symptom intelligence.
- Partner sharing with per-category permissions.
- Medical-grade prediction engine with uncertainty modelling.

## Implemented (with dates)
- 2026-06-11: Re-imported full repo into fresh environment (new preview URL
  mat-mobile-app.preview.emergentagent.com). Installed backend pip + frontend yarn deps,
  added JWT_SECRET to backend/.env, services running. Fresh DB: re-registered + verified
  demo@cycle.app / DemoPass123! and seeded 8 cycles (Nov 2025 – May 2026) → prediction
  2026-06-16 @ 95% confidence. Email stays in DEV mode (no RESEND_API_KEY; codes logged
  to backend err log). Verified via testing_agent: 13/13 backend smoke tests + full
  frontend login/tab walkthrough (iteration_9.json).
- 2026-06-10: Phase 2 final gap-closure (P2/P11/P14 persistence). The v2 engine already
  covered P1-P19; this iteration closed the spec's storage requirements in server.py:
  (a) P2 — prediction_history rows now store prediction_date + last_cycle_start and are
  auto-resolved with actual_period_start + prediction_error_days when the next period is
  logged (resolution runs in the /api/prediction persistence block); (b) P11 — monthly
  validation snapshots in db.validation_snapshots (unique user+month, idempotent),
  exposed as monthlySnapshots in GET /api/prediction/history; (c) P14 — persisted
  benchmark table db.benchmark_records (one row per walk-forward predicted/actual pair
  with error_days, confidence, engine_version, regularity, cycle_count). New unique
  indexes in db.py. New tests/test_phase2_persistence.py (11 tests). Verified via
  testing_agent: 218/218 backend tests, determinism + <60ms perf + frontend regression
  (iteration_8.json). NOTE: /api/auth/register rate limit (10/min + 30/hour, in-memory)
  trips large pytest runs — restart backend between suites to reset.
- 2026-06-10: P2 accuracy-over-time view + cleanup. New "Prediction accuracy" card on
  Insights (src/components/prediction/AccuracyTrail.tsx): back-tested metrics (±MAE days,
  hit rate, stability /100) from /api/prediction/history validationMetrics + an SVG trail
  chart of confidence & reliability across stored predictions; gated behind
  prediction.predictedDate (hidden for cold-start users). insights.tsx now also fetches
  /prediction/history?limit=24. Note: PredictionPanel was ALREADY split into prediction/
  sub-components (268 lines) — stale backlog item. Cleanup: removed unused ScrollView
  import (EventDetailSheet), migrated raw shadow* in partner/shared.tsx segBtnActive to
  Platform.select web boxShadow (+ added missing Platform import), moved pointerEvents
  prop -> style in ReliabilityRing. Seeded 8 cycles (Nov 2025-May 2026) + 9
  prediction_history rows for demo@cycle.app. Verified via testing_agent (iteration_7.json,
  all pass incl. new-user gating + partner-view regression).
- 2026-06-10: Re-imported full repo into fresh environment. Installed backend (pip) + frontend
  (yarn) deps, services running. DB was fresh: re-seeded verified demo user
  demo@cycle.app / DemoPass123! (creds in /app/memory/test_credentials.md). Email stays in
  DEV mode (no RESEND_API_KEY; codes logged to backend err log). Verified via testing_agent:
  13/13 backend smoke tests + full frontend tab walkthrough (iteration_6.json).
- 2026-06-09: Merged Timeline into Calendar. Tapping a calendar day now shows that day's
  full health events (water/meals/meds/mood/symptoms/activity/notes) with event-type filter
  chips + in-day search and a tap-to-open Event Details sheet (edit/delete). Removed the
  Timeline bottom tab (deleted app/(tabs)/timeline.tsx; logic moved to
  src/components/calendar/{eventUtils,DayEvents}.tsx). Calendar fetches /health-events per
  visible month (start_date/end_date) for accurate day data + "logged" dots. Fixed a
  pre-existing bug: EventDetailSheet used api.delete -> api.del; and stopped the closed
  bottom-sheet from leaking its "Event Details" content on web (render content only when an
  event is open; clear on close). Verified via testing_agent 11/11 (iteration_5.json) +
  empty-day screenshot. Seeded 6 demo health-events on 2026-06-09.
- 2026-06-09: Phase 2 P1+P2 follow-up. UI: surfaced Reliability Index (SVG ring +
  classification chip), P50/P75/P90/P95 prediction-interval bands, and a cold-start
  Data-Sufficiency note in the Insights screen (PredictionPanel.tsx); confidence now
  rounded to an integer for display. Persistence (P2): GET /api/prediction now upserts a
  longitudinal trail — db.prediction_history (unique user_id+prediction_id, idempotent via
  deterministic prediction_id) + db.validation_metrics (latest snapshot per user); added
  GET /api/prediction/history (auth, ?limit). Engine: outlierClassifications now expose a
  `type` alias alongside `outlier_type`. Verified via testing_agent: 10/10 new history-endpoint
  tests + 13/13 regression + frontend testIDs render (iteration_4/5 reports). Frontend is a
  STATIC expo web export — rebuild with `supervisorctl restart expo` after UI changes.
- 2026-06-09: Phase 2 — wired the deterministic ensemble engine (backend/prediction_engine_v2.py)
  into GET /api/prediction (replacing v1; all v1 core fields preserved for UI backward-compat).
  Adds 5-model ensemble (weighted/median/bayesian/trend/error-corrected, 40% cap per model,
  self-correcting weights from walk-forward backtest), Cycle Reliability Index (0-100),
  evidence-based confidence calibration, P50/P75/P90/P95 prediction intervals, change-point
  detection, advanced outlier classification (logging/short/long/missed), population priors for
  cold start (<6 cycles), trend forecasting, validation metrics (MAE/RMSE/success/stability),
  benchmark + reproducible audit trail, data-sufficiency levels capping confidence. Pure/
  deterministic, <100ms for 10yr history, NO external AI. Computed-only (no new DB persistence).
  Added tests/test_prediction_engine_v2.py (99% coverage, 171 unit tests) + updated endpoint
  determinism test to ignore auditTrail.generated_at metadata. Verified via testing_agent
  (13/13 live API, iteration_3.json).
- 2026-06-09: Imported full repo; backend healthy, login verified. Demo user
  demo@cycle.app / DemoPass123! seeded. Creds in /app/memory/test_credentials.md.
- 2026-06-09: Built Phase 1 MAT prediction engine (backend/prediction_engine.py) — pure,
  deterministic. Weighted prediction, MAD outlier detection (MeanAD fallback for MAD==0),
  walk-forward adaptive bias, confidence, classification, prediction window, 14-day
  probability distribution, trend detection, health flags. 98% coverage.

## Backlog / Remaining
- P2: Persist per-cycle is_outlier / prediction_error back onto cycle docs for history views.
- P2: Configure RESEND_API_KEY for real verification/reset emails before launch.
- P3 (polish): Remaining RN-Web console noise comes from libraries (React 19 element.ref
  via @gorhom/bottom-sheet) — app-level shadow*/pointerEvents are migrated.

## Next Tasks
- Optionally surface a compact prediction summary (window band + confidence ring) on the Today/home dashboard.
