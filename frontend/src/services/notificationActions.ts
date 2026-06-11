// Lock-screen / notification action handling + reminder scheduling glue.
//
// Runs on native only. Action buttons ("✓ Taken", "Snooze 15m", "+250 ml") fire even
// when the app is backgrounded, so the handlers talk to the API directly using the
// token persisted in secure storage (no in-memory session required).

import { Platform } from "react-native";
import { router } from "expo-router";

import { storage } from "@/src/utils/storage";
import { notificationService } from "@/src/services/notifications";
import {
  getReminderPrefs,
  type ReminderPrefs,
} from "@/src/services/notificationPrefs";
import { readWidgetData, refreshWidgets } from "@/src/widgets/widgetData";

const ACCESS_KEY = "access_token";
const BASE = (process.env.EXPO_PUBLIC_BACKEND_URL ?? "") + "/api";

function uuid(): string {
  return "act-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
}

async function authToken(): Promise<string | null> {
  const t = await storage.secureGet<string>(ACCESS_KEY, "");
  return t || null;
}

async function apiPost(path: string, body: Record<string, unknown>): Promise<boolean> {
  const token = await authToken();
  if (!token) return false;
  try {
    const res = await fetch(`${BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/** Build the daily recap body text from the latest cached widget data. */
export async function buildRecapBody(): Promise<string> {
  try {
    const d = await readWidgetData();
    if (!d.hasData) {
      return "See how today went — tap to open your daily recap.";
    }
    const parts: string[] = [];
    if (d.cycleDay > 0) parts.push(`Cycle day ${d.cycleDay}`);
    const waterPct = d.hydrationGoal > 0 ? Math.round((d.hydration / d.hydrationGoal) * 100) : 0;
    parts.push(`Water ${waterPct}%`);
    parts.push(`Meals ${d.mealsLogged}/4`);
    if (d.medicationsTaken > 0) parts.push(`Meds ${d.medicationsTaken}`);
    return parts.join(" · ") + " — tap for today's recap.";
  } catch {
    return "See how today went — tap to open your daily recap.";
  }
}

/**
 * Apply the user's reminder preferences (hydration + daily recap).
 * When `prompt` is true (user toggled a setting), request permission; otherwise only
 * (re)schedule if permission is already granted so we never prompt on app launch.
 * Returns whether notifications are permitted.
 */
export async function applyReminderPrefs(opts?: {
  prompt?: boolean;
  prefs?: ReminderPrefs;
}): Promise<boolean> {
  if (Platform.OS === "web" || !notificationService.isSupported()) return false;
  await notificationService.initialize();

  const granted = opts?.prompt
    ? await notificationService.requestPermissions()
    : await notificationService.hasPermission();
  if (!granted) return false;

  const prefs = opts?.prefs ?? (await getReminderPrefs());
  await notificationService.syncHydrationReminders(prefs.hydration, prefs.hydrationTimes);
  const body = await buildRecapBody();
  await notificationService.scheduleDailyRecap(prefs.recap, prefs.recapTime, body);
  return true;
}

/**
 * Handle a notification response (tap or action button). Safe to call on any platform.
 */
export async function handleNotificationResponse(response: any): Promise<void> {
  if (Platform.OS === "web") return;
  try {
    const actionId: string = response?.actionIdentifier ?? "";
    const data = (response?.notification?.request?.content?.data ?? {}) as Record<string, any>;
    const type = data.type;
    const isTap = !actionId || actionId === "expo.modules.notifications.actions.DEFAULT";

    if (type === "medication") {
      if (actionId === "TAKEN" && data.scheduleId) {
        await apiPost(`/medication-schedules/${data.scheduleId}/take`, {
          scheduled_time: data.time ?? null,
          timestamp: new Date().toISOString(),
          client_id: uuid(),
        });
        await refreshWidgets();
      } else if (actionId === "SNOOZE") {
        await notificationService.snoozeMedication(
          15,
          { scheduleId: data.scheduleId, name: data.name, time: data.time },
          data.name,
        );
      } else if (isTap) {
        router.push("/medications");
      }
    } else if (type === "hydration") {
      if (actionId === "WATER_250") {
        await apiPost("/water", { amount_ml: 250, client_id: uuid() });
        await refreshWidgets();
      } else if (isTap) {
        router.push("/");
      }
    } else if (type === "daily_recap" && isTap) {
      router.push("/");
    }
  } catch (e) {
    console.error("Failed to handle notification response:", e);
  }
}
