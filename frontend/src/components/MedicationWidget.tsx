// Medication tracking widget with smart reminders
import React, { useState, useCallback, useEffect } from 'react';
import {
  StyleSheet,
  View,
  Text,
  TouchableOpacity,
  ActivityIndicator,
  Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { useRouter } from 'expo-router';

import { colors, radius, spacing, type } from '@/src/theme';
import { api } from '@/src/api/client';

const ACCENT_COLOR = '#9B59B6';

type MedicationLog = {
  id: string;
  timestamp: string;
  data: {
    name: string;
    dosage?: string;
    category: string;
  };
};

type MedicationSummary = {
  count: number;
  medications: MedicationLog[];
};

type Props = {
  onLogMedication: () => void;
  refreshTrigger?: number;
};

// Group medications by name for display
const groupMedications = (meds: MedicationLog[]) => {
  const grouped: Record<string, { count: number; lastTaken: string; dosage?: string }> = {};
  meds.forEach(med => {
    const name = med.data.name;
    if (!grouped[name]) {
      grouped[name] = {
        count: 1,
        lastTaken: med.timestamp,
        dosage: med.data.dosage,
      };
    } else {
      grouped[name].count++;
      if (new Date(med.timestamp) > new Date(grouped[name].lastTaken)) {
        grouped[name].lastTaken = med.timestamp;
      }
    }
  });
  return grouped;
};

export default function MedicationWidget({ refreshTrigger }: Props) {
  const router = useRouter();
  const [data, setData] = useState<MedicationSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<number>(0);
  const [planned, setPlanned] = useState<number>(0);

  const fetchData = useCallback(async () => {
    try {
      const [result, today] = await Promise.all([
        api.get<MedicationSummary>('/medications/today'),
        api.get<{ pending: number; total: number }>('/medication-schedules/today'),
      ]);
      setData(result);
      setPending(today.pending);
      setPlanned(today.total);
    } catch (e) {
      console.error('Failed to fetch medication data:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData, refreshTrigger]);

  const goToReminders = useCallback(() => {
    if (Platform.OS !== 'web') {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    }
    router.push('/medications');
  }, [router]);

  if (loading) {
    return (
      <View style={[styles.container, styles.loadingContainer]}>
        <ActivityIndicator color={ACCENT_COLOR} />
      </View>
    );
  }

  const todayCount = data?.count ?? 0;
  const medications = data?.medications ?? [];
  const grouped = groupMedications(medications);
  const uniqueMeds = Object.keys(grouped);

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <View style={styles.titleRow}>
          <Ionicons name="medical" size={20} color={ACCENT_COLOR} />
          <Text style={styles.title}>Medications</Text>
        </View>
        <TouchableOpacity
          testID="medication-history-btn"
          onPress={goToReminders}
          style={styles.moreBtn}
          activeOpacity={0.7}
        >
          <Text style={styles.moreBtnText}>Manage</Text>
          <Ionicons name="chevron-forward" size={16} color={colors.text.tertiary} />
        </TouchableOpacity>
      </View>

      {/* Today's Summary */}
      <View style={styles.summaryCard}>
        <View style={styles.countCircle}>
          <Text style={styles.countText}>{todayCount}</Text>
        </View>
        <View style={styles.summaryInfo}>
          <Text style={styles.summaryTitle}>
            {todayCount === 0 ? 'No medications logged today' :
             todayCount === 1 ? '1 medication taken' : 
             `${todayCount} medications taken`}
          </Text>
          {uniqueMeds.length > 0 && (
            <Text style={styles.summarySubtext} numberOfLines={1}>
              {uniqueMeds.slice(0, 3).join(', ')}
              {uniqueMeds.length > 3 ? ` +${uniqueMeds.length - 3} more` : ''}
            </Text>
          )}
        </View>
      </View>

      {/* Recent Medications List */}
      {uniqueMeds.length > 0 && (
        <View style={styles.recentList}>
          {uniqueMeds.slice(0, 3).map((name, index) => {
            const med = grouped[name];
            const time = new Date(med.lastTaken).toLocaleTimeString([], { 
              hour: '2-digit', 
              minute: '2-digit' 
            });
            return (
              <View key={name} style={[
                styles.recentItem,
                index < Math.min(uniqueMeds.length - 1, 2) && styles.recentItemBorder
              ]}>
                <View style={styles.pillIcon}>
                  <Ionicons name="medical-outline" size={14} color={ACCENT_COLOR} />
                </View>
                <View style={styles.recentInfo}>
                  <Text style={styles.recentName}>{name}</Text>
                  {med.dosage && (
                    <Text style={styles.recentDosage}>{med.dosage}</Text>
                  )}
                </View>
                <Text style={styles.recentTime}>{time}</Text>
                {med.count > 1 && (
                  <View style={styles.countBadge}>
                    <Text style={styles.countBadgeText}>×{med.count}</Text>
                  </View>
                )}
              </View>
            );
          })}
        </View>
      )}

      {/* Today's planned doses banner */}
      {planned > 0 && (
        <View
          testID="medication-plan-banner"
          style={[styles.planBanner, pending === 0 && styles.planBannerDone]}
        >
          <Ionicons
            name={pending === 0 ? 'checkmark-circle' : 'time-outline'}
            size={16}
            color={pending === 0 ? colors.status.success : ACCENT_COLOR}
          />
          <Text style={styles.planBannerText}>
            {pending === 0
              ? `All ${planned} scheduled dose${planned === 1 ? '' : 's'} taken today`
              : `${planned - pending} of ${planned} scheduled doses taken · ${pending} pending`}
          </Text>
        </View>
      )}

      {/* Action Row */}
      <View style={styles.actionRow}>
        <TouchableOpacity
          testID="medication-manage-btn"
          style={styles.logBtn}
          onPress={goToReminders}
          activeOpacity={0.7}
        >
          <Ionicons name="alarm-outline" size={18} color="#fff" />
          <Text style={styles.logBtnText}>
            {planned > 0 ? "View today's doses" : 'Set up reminders'}
          </Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: colors.bg.primary,
    borderRadius: radius.lg,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.ui.border,
  },
  loadingContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 180,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.md,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  title: {
    ...type.h3,
    color: colors.text.primary,
    fontSize: 18,
  },
  moreBtn: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  moreBtnText: {
    ...type.bodySm,
    color: colors.text.tertiary,
  },
  summaryCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: ACCENT_COLOR + '10',
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  countCircle: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: ACCENT_COLOR,
    alignItems: 'center',
    justifyContent: 'center',
  },
  countText: {
    ...type.h2,
    color: '#fff',
    fontWeight: '700',
    fontSize: 20,
  },
  summaryInfo: {
    flex: 1,
    marginLeft: spacing.md,
  },
  summaryTitle: {
    ...type.body,
    color: colors.text.primary,
    fontWeight: '600',
  },
  summarySubtext: {
    ...type.bodySm,
    color: colors.text.secondary,
    marginTop: 2,
  },
  recentList: {
    backgroundColor: colors.bg.secondary,
    borderRadius: radius.md,
    marginBottom: spacing.md,
  },
  recentItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: spacing.sm,
    paddingHorizontal: spacing.md,
  },
  recentItemBorder: {
    borderBottomWidth: 1,
    borderBottomColor: colors.ui.divider,
  },
  pillIcon: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: ACCENT_COLOR + '15',
    alignItems: 'center',
    justifyContent: 'center',
  },
  recentInfo: {
    flex: 1,
    marginLeft: spacing.sm,
  },
  recentName: {
    ...type.bodySm,
    color: colors.text.primary,
    fontWeight: '500',
  },
  recentDosage: {
    ...type.caption,
    color: colors.text.tertiary,
    fontSize: 10,
  },
  recentTime: {
    ...type.caption,
    color: colors.text.tertiary,
  },
  countBadge: {
    backgroundColor: ACCENT_COLOR,
    borderRadius: 10,
    paddingHorizontal: 6,
    paddingVertical: 2,
    marginLeft: spacing.xs,
  },
  countBadgeText: {
    ...type.caption,
    color: '#fff',
    fontSize: 10,
    fontWeight: '600',
  },
  actionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  planBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    backgroundColor: ACCENT_COLOR + '12',
    borderRadius: radius.md,
    padding: spacing.sm,
    paddingHorizontal: spacing.md,
    marginBottom: spacing.md,
  },
  planBannerDone: {
    backgroundColor: colors.status.success + '15',
  },
  planBannerText: {
    ...type.bodySm,
    color: colors.text.secondary,
    flex: 1,
    fontWeight: '500',
  },
  logBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: ACCENT_COLOR,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    gap: spacing.xs,
  },
  logBtnText: {
    color: '#fff',
    fontWeight: '600',
    fontSize: 14,
  },
  reminderBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: ACCENT_COLOR + '15',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: ACCENT_COLOR + '30',
  },
  reminderBtnActive: {
    backgroundColor: ACCENT_COLOR,
    borderColor: ACCENT_COLOR,
  },
  reminderStatus: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: spacing.sm,
    gap: spacing.xs,
  },
  reminderText: {
    ...type.caption,
    color: colors.text.tertiary,
  },
  reminderTextActive: {
    color: colors.status.success,
  },
});
