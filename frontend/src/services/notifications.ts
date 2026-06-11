/**
 * Notification Service
 * 
 * Handles push notification setup, permissions, and local notifications.
 * Works on native (iOS/Android) only - web uses fallback/no-op implementations.
 */

import { Platform } from 'react-native';
import Constants from 'expo-constants';

// Only import expo-notifications on native platforms
let Notifications: typeof import('expo-notifications') | null = null;
let Device: typeof import('expo-device') | null = null;

// Dynamic imports for native-only modules
if (Platform.OS !== 'web') {
  try {
    Notifications = require('expo-notifications');
    Device = require('expo-device');
  } catch (e) {
    console.log('Native notification modules not available');
  }
}

export interface NotificationSettings {
  enabled: boolean;
  medicationReminders: boolean;
  hydrationReminders: boolean;
  periodReminders: boolean;
}

export interface ScheduledNotification {
  id: string;
  title: string;
  body: string;
  trigger: {
    hour: number;
    minute: number;
    repeats?: boolean;
  };
  data?: Record<string, any>;
}

// Default notification settings
const DEFAULT_SETTINGS: NotificationSettings = {
  enabled: true,
  medicationReminders: true,
  hydrationReminders: true,
  periodReminders: true,
};

class NotificationService {
  private isInitialized = false;
  private expoPushToken: string | null = null;

  /**
   * Initialize the notification service
   */
  async initialize(): Promise<boolean> {
    if (Platform.OS === 'web') {
      console.log('Notifications not supported on web');
      return false;
    }

    if (!Notifications || !Device) {
      console.log('Notification modules not loaded');
      return false;
    }

    if (this.isInitialized) {
      return true;
    }

    try {
      // Configure notification handler
      Notifications.setNotificationHandler({
        handleNotification: async () => ({
          shouldShowAlert: true,
          shouldPlaySound: true,
          shouldSetBadge: true,
          shouldShowBanner: true,
          shouldShowList: true,
        }),
      });

      await this.registerCategories();

      this.isInitialized = true;
      return true;
    } catch (error) {
      console.error('Failed to initialize notifications:', error);
      return false;
    }
  }

  /**
   * Request notification permissions
   */
  async requestPermissions(): Promise<boolean> {
    if (Platform.OS === 'web' || !Notifications || !Device) {
      return false;
    }

    try {
      // Check if running on physical device
      if (!Device.isDevice) {
        console.log('Push notifications require a physical device');
        return false;
      }

      const { status: existingStatus } = await Notifications.getPermissionsAsync();
      let finalStatus = existingStatus;

      if (existingStatus !== 'granted') {
        const { status } = await Notifications.requestPermissionsAsync();
        finalStatus = status;
      }

      if (finalStatus !== 'granted') {
        console.log('Notification permission not granted');
        return false;
      }

      return true;
    } catch (error) {
      console.error('Failed to request permissions:', error);
      return false;
    }
  }

  /**
   * Get the Expo Push Token for remote notifications
   */
  async getExpoPushToken(): Promise<string | null> {
    if (Platform.OS === 'web' || !Notifications || !Device) {
      return null;
    }

    if (this.expoPushToken) {
      return this.expoPushToken;
    }

    try {
      const hasPermission = await this.requestPermissions();
      if (!hasPermission) {
        return null;
      }

      // Get projectId from app config
      const projectId = Constants.expoConfig?.extra?.eas?.projectId
        ?? Constants.easConfig?.projectId;

      // Treat empty/placeholder values as "not configured". The real EAS project
      // ID is injected by the build/publish flow; remote push tokens only work
      // once that exists. Local scheduled notifications work without it.
      if (!projectId || projectId === 'your-project-id') {
        console.log(
          'EAS projectId not configured — remote push disabled (local notifications still work). ' +
          'A real projectId is set automatically when you publish/build the app.',
        );
        return null;
      }

      const token = await Notifications.getExpoPushTokenAsync({
        projectId,
      });

      this.expoPushToken = token.data;
      return this.expoPushToken;
    } catch (error) {
      console.error('Failed to get push token:', error);
      return null;
    }
  }

  /**
   * Schedule a local notification
   */
  async scheduleNotification(notification: ScheduledNotification): Promise<string | null> {
    if (Platform.OS === 'web' || !Notifications) {
      console.log('Scheduling notification (web mock):', notification.title);
      return notification.id;
    }

    try {
      const identifier = await Notifications.scheduleNotificationAsync({
        content: {
          title: notification.title,
          body: notification.body,
          data: notification.data || {},
          sound: true,
        },
        trigger: {
          type: Notifications.SchedulableTriggerInputTypes.DAILY,
          hour: notification.trigger.hour,
          minute: notification.trigger.minute,
        },
      });

      return identifier;
    } catch (error) {
      console.error('Failed to schedule notification:', error);
      return null;
    }
  }

  /**
   * Schedule a medication reminder
   */
  async scheduleMedicationReminder(
    medicationName: string,
    hour: number,
    minute: number,
    medicationId: string
  ): Promise<string | null> {
    return this.scheduleNotification({
      id: `medication-${medicationId}`,
      title: '💊 Medication Reminder',
      body: `Time to take ${medicationName}`,
      trigger: { hour, minute, repeats: true },
      data: { type: 'medication', medicationId },
    });
  }

  /**
   * Schedule a hydration reminder
   */
  async scheduleHydrationReminder(hour: number, minute: number): Promise<string | null> {
    return this.scheduleNotification({
      id: `hydration-${hour}-${minute}`,
      title: '💧 Stay Hydrated',
      body: "Don't forget to drink water!",
      trigger: { hour, minute, repeats: true },
      data: { type: 'hydration' },
    });
  }

  /**
   * Cancel a scheduled notification
   */
  async cancelNotification(identifier: string): Promise<void> {
    if (Platform.OS === 'web' || !Notifications) {
      console.log('Cancelling notification (web mock):', identifier);
      return;
    }

    try {
      await Notifications.cancelScheduledNotificationAsync(identifier);
    } catch (error) {
      console.error('Failed to cancel notification:', error);
    }
  }

  /**
   * Cancel all scheduled notifications
   */
  async cancelAllNotifications(): Promise<void> {
    if (Platform.OS === 'web' || !Notifications) {
      console.log('Cancelling all notifications (web mock)');
      return;
    }

    try {
      await Notifications.cancelAllScheduledNotificationsAsync();
    } catch (error) {
      console.error('Failed to cancel all notifications:', error);
    }
  }

  /**
   * Get all scheduled notifications
   */
  async getScheduledNotifications(): Promise<any[]> {
    if (Platform.OS === 'web' || !Notifications) {
      return [];
    }

    try {
      return await Notifications.getAllScheduledNotificationsAsync();
    } catch (error) {
      console.error('Failed to get scheduled notifications:', error);
      return [];
    }
  }

  /**
   * Add a listener for received notifications
   */
  addNotificationReceivedListener(
    callback: (notification: any) => void
  ): { remove: () => void } {
    if (Platform.OS === 'web' || !Notifications) {
      return { remove: () => {} };
    }

    return Notifications.addNotificationReceivedListener(callback);
  }

  /**
   * Add a listener for notification responses (when user taps notification)
   */
  addNotificationResponseListener(
    callback: (response: any) => void
  ): { remove: () => void } {
    if (Platform.OS === 'web' || !Notifications) {
      return { remove: () => {} };
    }

    return Notifications.addNotificationResponseReceivedListener(callback);
  }

  /**
   * Cancel only medication reminders (leaves other scheduled notifications intact).
   */
  async cancelMedicationReminders(): Promise<void> {
    if (Platform.OS === 'web' || !Notifications) return;
    try {
      const scheduled = await Notifications.getAllScheduledNotificationsAsync();
      for (const n of scheduled) {
        const data = (n.content?.data || {}) as Record<string, any>;
        if (data.type === 'medication') {
          await Notifications.cancelScheduledNotificationAsync(n.identifier);
        }
      }
    } catch (error) {
      console.error('Failed to cancel medication reminders:', error);
    }
  }

  /**
   * Re-sync all medication reminders from the user's schedules.
   * Cancels existing medication notifications, then schedules a repeating daily
   * notification for each planned time. No-op on web / Expo Go (no native module).
   * Returns the number of notifications scheduled (or -1 if unsupported).
   */
  async syncMedicationReminders(
    schedules: {
      id: string;
      name: string;
      dosage?: string | null;
      times: string[];
      enabled: boolean;
    }[],
  ): Promise<number> {
    if (Platform.OS === 'web' || !Notifications) return -1;
    if (!this.isSupported()) return -1;

    const hasPermission = await this.requestPermissions();
    if (!hasPermission) return -1;

    await this.cancelMedicationReminders();

    let count = 0;
    for (const sched of schedules) {
      if (!sched.enabled) continue;
      for (const t of sched.times || []) {
        const [hStr, mStr] = t.split(':');
        const hour = parseInt(hStr, 10);
        const minute = parseInt(mStr, 10);
        if (Number.isNaN(hour) || Number.isNaN(minute)) continue;
        try {
          await Notifications.scheduleNotificationAsync({
            content: {
              title: '\uD83D\uDC8A Time for your medication',
              body: sched.dosage
                ? `Take ${sched.name} (${sched.dosage})`
                : `Take ${sched.name}`,
              data: { type: 'medication', scheduleId: sched.id, name: sched.name, time: t },
              categoryIdentifier: 'MED_REMINDER',
              sound: true,
            },
            trigger: {
              type: Notifications.SchedulableTriggerInputTypes.DAILY,
              hour,
              minute,
            },
          });
          count += 1;
        } catch (error) {
          console.error('Failed to schedule med reminder:', error);
        }
      }
    }
    return count;
  }

  /**
   * Register notification categories so lock-screen action buttons appear.
   * MED_REMINDER -> "✓ Taken" / "Snooze 15m"; HYDRATION -> "+250 ml".
   */
  async registerCategories(): Promise<void> {
    if (Platform.OS === 'web' || !Notifications) return;
    try {
      await Notifications.setNotificationCategoryAsync('MED_REMINDER', [
        { identifier: 'TAKEN', buttonTitle: '\u2713 Taken', options: { opensAppToForeground: false } },
        { identifier: 'SNOOZE', buttonTitle: 'Snooze 15m', options: { opensAppToForeground: false } },
      ]);
      await Notifications.setNotificationCategoryAsync('HYDRATION', [
        { identifier: 'WATER_250', buttonTitle: '+250 ml', options: { opensAppToForeground: false } },
      ]);
      await Notifications.setNotificationCategoryAsync('DAILY_RECAP', []);
    } catch (error) {
      console.error('Failed to register notification categories:', error);
    }
  }

  /** True if notification permission is already granted (does NOT prompt). */
  async hasPermission(): Promise<boolean> {
    if (Platform.OS === 'web' || !Notifications || !Device) return false;
    try {
      const { status } = await Notifications.getPermissionsAsync();
      return status === 'granted';
    } catch {
      return false;
    }
  }

  /** Cancel all scheduled notifications whose data.type matches. */
  async cancelByType(type: string): Promise<void> {
    if (Platform.OS === 'web' || !Notifications) return;
    try {
      const scheduled = await Notifications.getAllScheduledNotificationsAsync();
      for (const n of scheduled) {
        const data = (n.content?.data || {}) as Record<string, any>;
        if (data.type === type) {
          await Notifications.cancelScheduledNotificationAsync(n.identifier);
        }
      }
    } catch (error) {
      console.error(`Failed to cancel ${type} notifications:`, error);
    }
  }

  /**
   * Schedule (or clear) fixed-time hydration reminders. No-op on web / Expo Go.
   */
  async syncHydrationReminders(enabled: boolean, times: string[]): Promise<number> {
    if (Platform.OS === 'web' || !Notifications || !this.isSupported()) return -1;
    await this.cancelByType('hydration');
    if (!enabled) return 0;
    let count = 0;
    for (const t of times) {
      const [hStr, mStr] = t.split(':');
      const hour = parseInt(hStr, 10);
      const minute = parseInt(mStr, 10);
      if (Number.isNaN(hour) || Number.isNaN(minute)) continue;
      try {
        await Notifications.scheduleNotificationAsync({
          content: {
            title: '\uD83D\uDCA7 Stay hydrated',
            body: 'Time for some water. Tap “+250 ml” to log a glass.',
            data: { type: 'hydration' },
            categoryIdentifier: 'HYDRATION',
            sound: true,
          },
          trigger: {
            type: Notifications.SchedulableTriggerInputTypes.DAILY,
            hour,
            minute,
          },
        });
        count += 1;
      } catch (error) {
        console.error('Failed to schedule hydration reminder:', error);
      }
    }
    return count;
  }

  /**
   * Schedule (or clear) the daily recap digest at the given time.
   * `body` is built by the caller from the latest cached summary. No-op on web.
   */
  async scheduleDailyRecap(enabled: boolean, time: string, body: string): Promise<boolean> {
    if (Platform.OS === 'web' || !Notifications || !this.isSupported()) return false;
    await this.cancelByType('daily_recap');
    if (!enabled) return false;
    const [hStr, mStr] = time.split(':');
    const hour = parseInt(hStr, 10);
    const minute = parseInt(mStr, 10);
    if (Number.isNaN(hour) || Number.isNaN(minute)) return false;
    try {
      await Notifications.scheduleNotificationAsync({
        content: {
          title: '\u2728 Your daily recap',
          body,
          data: { type: 'daily_recap' },
          categoryIdentifier: 'DAILY_RECAP',
          sound: true,
        },
        trigger: {
          type: Notifications.SchedulableTriggerInputTypes.DAILY,
          hour,
          minute,
        },
      });
      return true;
    } catch (error) {
      console.error('Failed to schedule daily recap:', error);
      return false;
    }
  }

  /** Re-fire a medication reminder after a short snooze (one-off). */
  async snoozeMedication(
    minutes: number,
    data: Record<string, any>,
    name?: string,
  ): Promise<void> {
    if (Platform.OS === 'web' || !Notifications) return;
    try {
      await Notifications.scheduleNotificationAsync({
        content: {
          title: '\uD83D\uDC8A Medication reminder (snoozed)',
          body: name ? `Take ${name}` : 'Time to take your medication',
          data: { ...data, type: 'medication' },
          categoryIdentifier: 'MED_REMINDER',
          sound: true,
        },
        trigger: {
          type: Notifications.SchedulableTriggerInputTypes.TIME_INTERVAL,
          seconds: Math.max(60, minutes * 60),
        },
      });
    } catch (error) {
      console.error('Failed to snooze medication reminder:', error);
    }
  }

  /**
   * Check if notifications are supported on this platform
   */
  isSupported(): boolean {
    return Platform.OS !== 'web' && !!Notifications && !!Device;
  }
}

// Export singleton instance
export const notificationService = new NotificationService();
export default notificationService;
