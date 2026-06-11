// Sexual activity tracking widget for dashboard - Privacy focused
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

import { colors, radius, spacing, type } from '@/src/theme';
import { api } from '@/src/api/client';

const ACCENT_COLOR = '#E91E63';

type ActivityLog = {
  id: string;
  timestamp: string;
  data: {
    protection_used: boolean;
    partner_present: boolean;
  };
  note?: string;
};

type ActivityHistory = {
  days: number;
  total_entries: number;
  logs: ActivityLog[];
};

type Props = {
  onLogActivity: () => void;
  refreshTrigger?: number;
};

export default function SexualActivityWidget({ onLogActivity, refreshTrigger }: Props) {
  const [data, setData] = useState<ActivityHistory | null>(null);
  const [loading, setLoading] = useState(true);
  const [todayLogged, setTodayLogged] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const result = await api.get<ActivityHistory>('/sexual-activity/history?days=30');
      setData(result);
      
      // Check if logged today
      const today = new Date().toISOString().split('T')[0];
      const loggedToday = result.logs.some(log => log.timestamp.startsWith(today));
      setTodayLogged(loggedToday);
    } catch (e) {
      console.error('Failed to fetch activity history:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData, refreshTrigger]);

  const handleQuickLog = useCallback(async () => {
    if (Platform.OS !== 'web') {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    }
    onLogActivity();
  }, [onLogActivity]);

  if (loading) {
    return (
      <View style={[styles.container, styles.loadingContainer]}>
        <ActivityIndicator color={ACCENT_COLOR} />
      </View>
    );
  }

  const totalThisMonth = data?.total_entries ?? 0;
  
  // Calculate last logged date
  const lastLog = data?.logs?.[0];
  const lastLogDate = lastLog ? new Date(lastLog.timestamp) : null;
  const daysSinceLastLog = lastLogDate 
    ? Math.floor((Date.now() - lastLogDate.getTime()) / (1000 * 60 * 60 * 24))
    : null;

  // Get this week's count
  const oneWeekAgo = new Date();
  oneWeekAgo.setDate(oneWeekAgo.getDate() - 7);
  const thisWeekCount = data?.logs?.filter(log => 
    new Date(log.timestamp) >= oneWeekAgo
  ).length ?? 0;

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <View style={styles.titleRow}>
          <Ionicons name="heart" size={20} color={ACCENT_COLOR} />
          <Text style={styles.title}>Intimacy</Text>
          <View style={styles.privacyBadge}>
            <Ionicons name="lock-closed" size={10} color={colors.text.tertiary} />
            <Text style={styles.privacyText}>Private</Text>
          </View>
        </View>
        <TouchableOpacity
          onPress={onLogActivity}
          style={styles.moreBtn}
          activeOpacity={0.7}
        >
          <Text style={styles.moreBtnText}>History</Text>
          <Ionicons name="chevron-forward" size={16} color={colors.text.tertiary} />
        </TouchableOpacity>
      </View>

      {/* Stats Cards */}
      <View style={styles.statsRow}>
        <View style={styles.statCard}>
          <Text style={styles.statValue}>{thisWeekCount}</Text>
          <Text style={styles.statLabel}>This week</Text>
        </View>
        
        <View style={styles.statDivider} />
        
        <View style={styles.statCard}>
          <Text style={styles.statValue}>{totalThisMonth}</Text>
          <Text style={styles.statLabel}>This month</Text>
        </View>
        
        <View style={styles.statDivider} />
        
        <View style={styles.statCard}>
          <Text style={[styles.statValue, styles.smallerValue]}>
            {daysSinceLastLog !== null 
              ? daysSinceLastLog === 0 
                ? 'Today' 
                : `${daysSinceLastLog}d ago`
              : '—'}
          </Text>
          <Text style={styles.statLabel}>Last logged</Text>
        </View>
      </View>

      {/* Quick Log Button */}
      <View style={styles.actionRow}>
        {todayLogged ? (
          <View style={styles.loggedBadge}>
            <Ionicons name="checkmark-circle" size={16} color={colors.status.success} />
            <Text style={styles.loggedText}>Logged today</Text>
          </View>
        ) : (
          <TouchableOpacity
            style={styles.logBtn}
            onPress={handleQuickLog}
            activeOpacity={0.7}
          >
            <Ionicons name="add" size={18} color="#fff" />
            <Text style={styles.logBtnText}>Log Activity</Text>
          </TouchableOpacity>
        )}
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
    minHeight: 140,
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
  privacyBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.bg.tertiary,
    paddingHorizontal: spacing.xs,
    paddingVertical: 2,
    borderRadius: radius.sm,
    marginLeft: spacing.xs,
    gap: 2,
  },
  privacyText: {
    ...type.caption,
    color: colors.text.tertiary,
    fontSize: 9,
    textTransform: 'uppercase',
  },
  moreBtn: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  moreBtnText: {
    ...type.bodySm,
    color: colors.text.tertiary,
  },
  statsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.bg.secondary,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  statCard: {
    flex: 1,
    alignItems: 'center',
  },
  statDivider: {
    width: 1,
    height: 30,
    backgroundColor: colors.ui.divider,
  },
  statValue: {
    ...type.h2,
    color: ACCENT_COLOR,
    fontSize: 20,
    fontWeight: '700',
  },
  smallerValue: {
    fontSize: 14,
  },
  statLabel: {
    ...type.caption,
    color: colors.text.tertiary,
    marginTop: 2,
    fontSize: 10,
  },
  actionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  logBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: ACCENT_COLOR,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    gap: spacing.xs,
  },
  logBtnText: {
    color: '#fff',
    fontWeight: '600',
    fontSize: 14,
  },
  loggedBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    backgroundColor: colors.status.success + '15',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
  },
  loggedText: {
    ...type.bodySm,
    color: colors.status.success,
    fontWeight: '600',
  },
});
