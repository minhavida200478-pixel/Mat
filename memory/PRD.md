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
- 2026-06-11: Phase 3 — "Verified Forecasting Improvements Only" engine v3
  (backend/prediction_engine_v3.py, v3.0.0 / verified-forecast-v1) now serves
  GET /api/prediction. Every enhancement is EVIDENCE-GATED per user via walk-forward
  backtesting (P12): bias correction, dampening, strategy/window selection,
  conformal vs heuristic intervals, direct-vs-traditional quantiles, confidence
  estimator all activate only if they improve MAE/calibration/coverage. New per spec:
  P3 conformal intervals (own out-of-sample signed errors, coverage audit, rejection
  fallback), P4 adaptive lookback windows {3,6,12,24}, P5 direct quantile forecasting
  (P10–P90, pinball-loss gate), P7 distribution/intervals/quantiles all from ONE
  empirical error CDF (14-row v1-compatible window), P8 calibration engine (bucketed
  CE, <5% target, gated shrinkage), P9 forecast-stability metrics + gated dampening
  (±2d clamp), P11 activeForecastingStrategy (margin-protected 0.15d), P14 NEW
  GET /api/prediction/monitoring (30/90/365-day/lifetime: MAE/RMSE/median/calibration/
  p95-error/coverage). prediction_history rows now persist active_strategy,
  optimal_window, model_accuracy, stability_score, quantile_method, p95 bounds.
  Output is a superset of v2 (UI untouched, fully compatible). v2 kept importable
  for benchmark gates. Tests: tests/test_prediction_engine_v3.py (51, 97% cov),
  tests/test_v3_benchmark_gate.py (13 — v3 must not regress vs v2 + MAE success
  criteria: very regular <1.5, regular <2.0, mod-irregular <3.0 on AR(1) cohorts +
  p95 coverage + calibration), tests/test_v3_endpoint.py (5). Existing v2/phase2
  suites updated to accept 3.0.0 and conformal interval source; all green
  (235 engine + 52 API). Verified via testing_agent iteration_10 (11/11 integration
  + frontend regression). NOTE: demo user (8 cycles) correctly gates conformal/
  direct-quantile OFF (insufficient evidence) — expected behavior.
- 2026-06-11: Phase 2 spec re-submitted by user — full audit confirmed ALL 20 priorities
  are already implemented in this environment (engine v2.0.0 / ensemble-v1). Verified by
  running suites here: 171/171 engine unit tests with 99% line coverage on
  prediction_engine_v2.py (P20 ≥95% met), 21/21 phase2-persistence + history-endpoint
  tests, 26/26 prediction endpoint tests (218 total). Live /api/prediction response
  carries all Phase 2 fields (models, modelWeights ≤0.40 cap, reliabilityIndex,
  predictionIntervals p50–p95, dataSufficiency, trendForecast, changePoints,
  outlierClassifications, healthFlags, populationPrior, auditTrail, engineVersion,
  validationMetrics, predictionErrors/rolling, confidenceSource=historical_accuracy).
  Perf: local API ~7ms (<200ms P19). Field-name mapping vs spec: models=model
  predictions, healthFlags=medical flags, predictionErrors=rolling errors. Reminder:
  in-memory register rate limit (10/min, 30/hour) — restart backend between large
  API test suites.
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
