// Persisted user preferences for on-device reminders (local notifications).
import { storage } from "@/src/utils/storage";

const PREFS_KEY = "reminder_prefs_v1";

export interface ReminderPrefs {
  hydration: boolean;        // hydration reminders on/off
  hydrationTimes: string[];  // user-chosen "HH:MM" 24h times
  recap: boolean;            // daily recap digest
  recapTime: string;         // "HH:MM" 24h for the daily recap
}

// Default hydration reminder times (24h) — fully editable by the user.
export const DEFAULT_HYDRATION_TIMES = ["10:00", "13:00", "16:00", "19:00"];

export const DEFAULT_PREFS: ReminderPrefs = {
  hydration: true,
  hydrationTimes: DEFAULT_HYDRATION_TIMES,
  recap: true,
  recapTime: "20:00",
};

export async function getReminderPrefs(): Promise<ReminderPrefs> {
  const raw = await storage.getItem<string>(PREFS_KEY, "");
  if (!raw) return { ...DEFAULT_PREFS };
  try {
    const parsed = JSON.parse(raw);
    const merged = { ...DEFAULT_PREFS, ...parsed };
    if (!Array.isArray(merged.hydrationTimes) || merged.hydrationTimes.length === 0) {
      merged.hydrationTimes = [...DEFAULT_HYDRATION_TIMES];
    }
    return merged;
  } catch {
    return { ...DEFAULT_PREFS };
  }
}

export async function saveReminderPrefs(prefs: ReminderPrefs): Promise<void> {
  await storage.setItem(PREFS_KEY, JSON.stringify(prefs));
}
