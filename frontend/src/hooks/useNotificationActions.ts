import { useEffect } from "react";
import { Platform } from "react-native";

import { notificationService } from "@/src/services/notifications";
import {
  applyReminderPrefs,
  handleNotificationResponse,
} from "@/src/services/notificationActions";

/**
 * App-wide notification wiring (native only):
 *  - registers categories + response listener (handles lock-screen action buttons)
 *  - re-applies hydration / daily-recap reminders when permission is already granted
 *  - handles a cold-start launch from tapping a notification
 */
export function useNotificationActions() {
  useEffect(() => {
    if (Platform.OS === "web" || !notificationService.isSupported()) return;

    let sub: { remove: () => void } | null = null;

    (async () => {
      await notificationService.initialize();
      await applyReminderPrefs({ prompt: false });
    })();

    sub = notificationService.addNotificationResponseListener(handleNotificationResponse);

    // Cold start: app opened by tapping a notification.
    (async () => {
      try {
        const Notifications = require("expo-notifications");
        const last = await Notifications.getLastNotificationResponseAsync();
        if (last) await handleNotificationResponse(last);
      } catch {
        /* native module unavailable */
      }
    })();

    return () => {
      sub?.remove();
    };
  }, []);
}
