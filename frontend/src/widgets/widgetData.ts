// Local cache + sync layer for Android home-screen widgets.
//
// The widget task handler runs in a HEADLESS context (no React app, no in-memory
// session). It reads the latest stats from this cache so it can render without a
// network round-trip. The app refreshes the cache whenever it loads/changes data.
//
// Quick-log actions fired from a widget POST directly to the backend using the
// access token persisted in secure storage, then optimistically update the cache.

import { Platform } from "react-native";

import { storage } from "../utils/storage";
import { currentPhaseLabel } from "../utils/cycle";

const WIDGET_DATA_KEY = "cycle_widget_data_v1";
const ACCESS_KEY = "access_token";
const BASE = (process.env.EXPO_PUBLIC_BACKEND_URL ?? "") + "/api";

export type WidgetData = {
  hasData: boolean;
  cycleDay: number;
  phase: string;
  daysUntilNextPeriod: number | null;
  nextPeriodDate: string | null; // ISO yyyy-mm-dd
  hydration: number; // ml
  hydrationGoal: number; // ml
  hydrationGoalMet: boolean;
  mealsLogged: number; // 0-4
  medicationsTaken: number;
  streakDays: number;
  updatedAt: string;
};

export const DEFAULT_WIDGET_DATA: WidgetData = {
  hasData: false,
  cycleDay: 0,
  phase: "Get started",
  daysUntilNextPeriod: null,
  nextPeriodDate: null,
  hydration: 0,
  hydrationGoal: 2000,
  hydrationGoalMet: false,
  mealsLogged: 0,
  medicationsTaken: 0,
  streakDays: 0,
  updatedAt: "",
};

export function localToday(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate(),
  ).padStart(2, "0")}`;
}

// ----------------------------- cache I/O -----------------------------
export async function readWidgetData(): Promise<WidgetData> {
  const raw = await storage.getItem<string>(WIDGET_DATA_KEY, "");
  if (!raw) return { ...DEFAULT_WIDGET_DATA };
  try {
    return { ...DEFAULT_WIDGET_DATA, ...JSON.parse(raw) };
  } catch {
    return { ...DEFAULT_WIDGET_DATA };
  }
}

export async function saveWidgetData(data: WidgetData): Promise<void> {
  await storage.setItem(WIDGET_DATA_KEY, JSON.stringify(data));
}

// ----------------------------- widget refresh -----------------------------
// Ask Android to re-render every widget we own. No-op anywhere the native module
// is unavailable (Expo Go, web preview, iOS) so it's always safe to call.
export async function refreshWidgets(): Promise<void> {
  if (Platform.OS !== "android") return;
  try {
    // Lazy require: the native module isn't present in Expo Go / web.
    const { requestWidgetUpdate } = require("react-native-android-widget");
    const React = require("react");
    const { HealthSummaryWidget } = require("./HealthSummaryWidget");
    const { QuickLogWidget } = require("./QuickLogWidget");
    const { NextPeriodWidget } = require("./NextPeriodWidget");

    const data = await readWidgetData();
    await Promise.all([
      requestWidgetUpdate({
        widgetName: "HealthSummary",
        renderWidget: () => React.createElement(HealthSummaryWidget, data),
      }),
      requestWidgetUpdate({
        widgetName: "QuickLog",
        renderWidget: () => React.createElement(QuickLogWidget, data),
      }),
      requestWidgetUpdate({
        widgetName: "NextPeriod",
        renderWidget: () => React.createElement(NextPeriodWidget, data),
      }),
    ]);
  } catch {
    // Native widget module unavailable — ignore.
  }
}

// ----------------------------- app/headless -> cache sync -----------------------------
async function authToken(): Promise<string | null> {
  const t = await storage.secureGet<string>(ACCESS_KEY, "");
  return t || null;
}

async function apiGet<T = any>(path: string): Promise<T | null> {
  const token = await authToken();
  if (!token) return null;
  try {
    const res = await fetch(`${BASE}${path}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

// Fetch the aggregated widget summary, map it to the cache shape, persist it, and
// re-render the widgets. Reads the token straight from secure storage so it works
// both in the foreground app AND in the headless background task. Android-only.
export async function fetchAndCacheWidgetData(): Promise<boolean> {
  if (Platform.OS !== "android") return false;
  const summary = await apiGet<any>(`/widget-summary?today=${localToday()}`);
  if (!summary) return false;

  const p = summary.prediction;
  const { phase } = currentPhaseLabel(p);
  const data: WidgetData = {
    hasData: !!p?.has_data,
    cycleDay: p?.cycle_day && p.cycle_day > 0 ? p.cycle_day : 0,
    phase,
    daysUntilNextPeriod:
      typeof p?.days_until_next_period === "number" ? p.days_until_next_period : null,
    nextPeriodDate: p?.next_period_date ?? null,
    hydration: summary.hydration ?? 0,
    hydrationGoal: summary.hydration_goal ?? 2000,
    hydrationGoalMet: !!summary.hydration_goal_met,
    mealsLogged: summary.meals_logged ?? 0,
    medicationsTaken: summary.medications_taken ?? 0,
    streakDays: summary.streak_days ?? 0,
    updatedAt: new Date().toISOString(),
  };
  await saveWidgetData(data);
  await refreshWidgets();
  return true;
}

// Backwards-compatible name used by the dashboard.
export async function syncWidgetData(): Promise<void> {
  await fetchAndCacheWidgetData();
}

// ----------------------------- headless quick-log -----------------------------
async function apiPost(path: string, body: Record<string, unknown>): Promise<boolean> {
  const token = await authToken();
  if (!token) return false;
  try {
    const res = await fetch(`${BASE}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(body),
    });
    return res.ok;
  } catch {
    return false;
  }
}

// Auto-pick the meal slot for one-tap meal logging based on the local hour.
export function suggestedMealType(): string {
  const hour = new Date().getHours();
  if (hour >= 6 && hour < 11) return "breakfast";
  if (hour >= 11 && hour < 15) return "lunch";
  if (hour >= 17 && hour < 21) return "dinner";
  return "snack";
}

export async function logWaterFromWidget(amountMl: number): Promise<void> {
  const ok = await apiPost("/water", { amount_ml: amountMl });
  // Optimistically reflect the change locally so the widget updates immediately,
  // even if a full re-sync from the API is delayed.
  const data = await readWidgetData();
  if (ok) data.hydration = data.hydration + amountMl;
  await saveWidgetData(data);
}

export async function logMealFromWidget(): Promise<void> {
  const ok = await apiPost("/meals", { meal_type: suggestedMealType() });
  const data = await readWidgetData();
  if (ok) data.mealsLogged = Math.min(4, data.mealsLogged + 1);
  await saveWidgetData(data);
}

export async function logPeriodFromWidget(): Promise<void> {
  await apiPost("/cycles", { start_date: localToday() });
  // Cycle predictions recompute server-side; trigger a fresh sync on next app focus.
}
