/**
 * Periodic background refresh for the Android home-screen widgets.
 *
 * The OS wakes the app headlessly (roughly every `minimumInterval` minutes, subject
 * to battery/network/system policy) and runs the task, which pulls the latest
 * widget-summary from the backend and re-renders the widgets — so they stay fresh
 * even when the app is never opened.
 *
 * NOTE: Native-build only. expo-background-task does NOT run in Expo Go or web.
 * The task MUST be defined at module scope so the OS can find it on a cold headless
 * launch; this module is therefore imported (Android-only) from index.js at startup.
 */
import * as BackgroundTask from "expo-background-task";
import * as TaskManager from "expo-task-manager";
import { Platform } from "react-native";

import { fetchAndCacheWidgetData } from "./widgetData";

export const WIDGET_REFRESH_TASK = "cycle-widget-refresh";

// Defined at global scope (see note above).
TaskManager.defineTask(WIDGET_REFRESH_TASK, async () => {
  try {
    await fetchAndCacheWidgetData();
    return BackgroundTask.BackgroundTaskResult.Success;
  } catch {
    return BackgroundTask.BackgroundTaskResult.Failed;
  }
});

export async function registerWidgetBackgroundTask(): Promise<void> {
  if (Platform.OS !== "android") return;
  try {
    const status = await BackgroundTask.getStatusAsync();
    if (status === BackgroundTask.BackgroundTaskStatus.Restricted) return;

    const alreadyRegistered = await TaskManager.isTaskRegisteredAsync(WIDGET_REFRESH_TASK);
    if (!alreadyRegistered) {
      // 30 min is a reasonable cadence for habit stats; the OS may run it less often.
      await BackgroundTask.registerTaskAsync(WIDGET_REFRESH_TASK, { minimumInterval: 30 });
    }
  } catch {
    // Native module unavailable (Expo Go) — ignore.
  }
}

export async function unregisterWidgetBackgroundTask(): Promise<void> {
  if (Platform.OS !== "android") return;
  try {
    const alreadyRegistered = await TaskManager.isTaskRegisteredAsync(WIDGET_REFRESH_TASK);
    if (alreadyRegistered) await BackgroundTask.unregisterTaskAsync(WIDGET_REFRESH_TASK);
  } catch {
    // ignore
  }
}
