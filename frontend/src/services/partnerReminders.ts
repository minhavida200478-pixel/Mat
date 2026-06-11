// Opt-in, on-device reminders a partner can enable for the person they support.
// Local notifications only (no remote push) — native build only; no-op on web / Expo Go.
import { Platform } from "react-native";

import notificationService from "@/src/services/notifications";
import { storage } from "@/src/utils/storage";

const KEY = (linkId: string) => `partner_reminders_${linkId}`;

export interface PartnerReminderPrefs {
  period: boolean; // period approaching
  hydration: boolean; // hydration goal incomplete
  medication: boolean; // medication check-in
}

export const DEFAULT_PARTNER_REMINDERS: PartnerReminderPrefs = {
  period: false,
  hydration: false,
  medication: false,
};

export async function getPartnerReminders(linkId: string): Promise<PartnerReminderPrefs> {
  const raw = await storage.getItem<string>(KEY(linkId), "");
  if (!raw) return { ...DEFAULT_PARTNER_REMINDERS };
  try {
    return { ...DEFAULT_PARTNER_REMINDERS, ...JSON.parse(raw) };
  } catch {
    return { ...DEFAULT_PARTNER_REMINDERS };
  }
}

export async function savePartnerReminders(
  linkId: string,
  prefs: PartnerReminderPrefs,
): Promise<void> {
  await storage.setItem(KEY(linkId), JSON.stringify(prefs));
}

interface ReminderContext {
  name: string;
  daysUntilPeriod?: number | null;
  hydrationPct?: number | null;
}

/**
 * (Re)schedule the partner's opt-in reminders. Cancels any prior reminders for
 * this link first, then schedules a daily local notification per enabled type.
 * No-op (returns false) on web / Expo Go where local notifications aren't available.
 */
export async function applyPartnerReminders(
  linkId: string,
  prefs: PartnerReminderPrefs,
  ctx: ReminderContext,
): Promise<boolean> {
  if (Platform.OS === "web" || !notificationService.isSupported()) return false;

  await notificationService.cancelByType(`partner_period_${linkId}`);
  await notificationService.cancelByType(`partner_hydration_${linkId}`);
  await notificationService.cancelByType(`partner_medication_${linkId}`);

  const name = ctx.name || "your partner";

  if (prefs.period) {
    const du = ctx.daysUntilPeriod;
    const body =
      typeof du === "number" && du >= 0
        ? `${name}'s period is expected ${
            du === 0 ? "today" : du === 1 ? "tomorrow" : `in ${du} days`
          }.`
        : `${name}'s period may be approaching.`;
    await notificationService.scheduleNotification({
      id: `partner_period_${linkId}`,
      title: "Cycle reminder",
      body,
      trigger: { hour: 9, minute: 0, repeats: true },
      data: { type: `partner_period_${linkId}` },
    });
  }

  if (prefs.hydration) {
    await notificationService.scheduleNotification({
      id: `partner_hydration_${linkId}`,
      title: "Hydration check-in",
      body: `See if ${name} has finished today's water goal.`,
      trigger: { hour: 18, minute: 0, repeats: true },
      data: { type: `partner_hydration_${linkId}` },
    });
  }

  if (prefs.medication) {
    await notificationService.scheduleNotification({
      id: `partner_medication_${linkId}`,
      title: "Medication check-in",
      body: `Check whether ${name} has taken today's medication.`,
      trigger: { hour: 9, minute: 30, repeats: true },
      data: { type: `partner_medication_${linkId}` },
    });
  }

  return true;
}
