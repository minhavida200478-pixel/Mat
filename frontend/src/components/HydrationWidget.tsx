// Hydration progress widget for dashboard
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
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  withSpring,
  Easing,
} from 'react-native-reanimated';

import { colors, radius, spacing, type } from '@/src/theme';
import { api } from '@/src/api/client';
import { syncWrite } from '@/src/sync/offlineQueue';

type WaterSummary = {
  date: string;
  total_ml: number;
  goal_ml: number;
  percentage: number;
  remaining_ml: number;
  logs: Array<{ id: string; amount_ml: number; timestamp: string; note?: string }>;
};

type Props = {
  onLogWater: () => void;
  onLogged?: () => void;
  refreshTrigger?: number;
};

export default function HydrationWidget({ onLogWater, onLogged, refreshTrigger }: Props) {
  const [data, setData] = useState<WaterSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [quickLogging, setQuickLogging] = useState(false);
  
  const progressWidth = useSharedValue(0);
  const pulseScale = useSharedValue(1);

  const fetchData = useCallback(async () => {
    try {
      const result = await api.get<WaterSummary>('/water/today');
      setData(result);
      progressWidth.value = withTiming(result.percentage, {
        duration: 600,
        easing: Easing.out(Easing.cubic),
      });
    } catch (e) {
      console.error('Failed to fetch water data:', e);
    } finally {
      setLoading(false);
    }
  }, [progressWidth]);

  useEffect(() => {
    fetchData();
  }, [fetchData, refreshTrigger]);

  const handleQuickLog = useCallback(async () => {
    if (Platform.OS !== 'web') {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    }
    setQuickLogging(true);
    
    // Pulse animation
    pulseScale.value = withSpring(1.1, { damping: 10 }, () => {
      pulseScale.value = withSpring(1);
    });
    
    try {
      const res = await syncWrite('POST', '/water', { amount_ml: 250 }, 'Water +250ml');
      if (Platform.OS !== 'web') {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      }
      if (res.queued) {
        // Offline: optimistically reflect the +250ml locally; it will sync later.
        setData((prev) => {
          if (!prev) return prev;
          const total = prev.total_ml + 250;
          const pct = prev.goal_ml > 0 ? Math.min(100, Math.round((total / prev.goal_ml) * 100)) : 0;
          progressWidth.value = withTiming(pct, { duration: 400, easing: Easing.out(Easing.cubic) });
          return { ...prev, total_ml: total, percentage: pct, remaining_ml: Math.max(0, prev.goal_ml - total) };
        });
      } else {
        fetchData();
      }
      onLogged?.();
    } catch (e) {
      console.error('Failed to quick log water:', e);
    } finally {
      setQuickLogging(false);
    }
  }, [fetchData, pulseScale, progressWidth, onLogged]);

  const animatedProgressStyle = useAnimatedStyle(() => ({
    width: `${progressWidth.value}%`,
  }));

  const animatedIconStyle = useAnimatedStyle(() => ({
    transform: [{ scale: pulseScale.value }],
  }));

  if (loading) {
    return (
      <View style={[styles.container, styles.loadingContainer]}>
        <ActivityIndicator color={colors.brand.primary} />
      </View>
    );
  }

  const percentage = data?.percentage ?? 0;
  const totalMl = data?.total_ml ?? 0;
  const goalMl = data?.goal_ml ?? 2000;
  const remaining = data?.remaining_ml ?? goalMl;
  const isGoalMet = percentage >= 100;

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <View style={styles.titleRow}>
          <Ionicons name="water" size={20} color="#4A90D9" />
          <Text style={styles.title}>Hydration</Text>
        </View>
        <TouchableOpacity
          onPress={onLogWater}
          style={styles.moreBtn}
          activeOpacity={0.7}
        >
          <Text style={styles.moreBtnText}>Details</Text>
          <Ionicons name="chevron-forward" size={16} color={colors.text.tertiary} />
        </TouchableOpacity>
      </View>

      <View style={styles.progressSection}>
        <View style={styles.progressBar}>
          <Animated.View 
            style={[
              styles.progressFill, 
              animatedProgressStyle,
              isGoalMet && styles.progressFillComplete
            ]} 
          />
        </View>
        <View style={styles.statsRow}>
          <Text style={styles.statsText}>
            <Text style={styles.statsBold}>{totalMl}ml</Text> / {goalMl}ml
          </Text>
          <Text style={[styles.percentText, isGoalMet && styles.percentTextComplete]}>
            {Math.round(percentage)}%
          </Text>
        </View>
      </View>

      <View style={styles.actionRow}>
        <TouchableOpacity
          style={styles.quickLogBtn}
          onPress={handleQuickLog}
          disabled={quickLogging}
          activeOpacity={0.7}
          testID="hydration-quick-log-btn"
        >
          <Animated.View style={animatedIconStyle}>
            {quickLogging ? (
              <ActivityIndicator color="#fff" size="small" />
            ) : (
              <Ionicons name="add" size={20} color="#fff" />
            )}
          </Animated.View>
          <Text style={styles.quickLogText}>+250ml</Text>
        </TouchableOpacity>

        <View style={styles.remainingInfo}>
          {isGoalMet ? (
            <View style={styles.goalMetBadge}>
              <Ionicons name="checkmark-circle" size={16} color={colors.status.success} />
              <Text style={styles.goalMetText}>Goal reached!</Text>
            </View>
          ) : (
            <>
              <Text style={styles.remainingLabel}>Remaining</Text>
              <Text style={styles.remainingValue}>{remaining}ml</Text>
            </>
          )}
        </View>
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
  moreBtn: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  moreBtnText: {
    ...type.bodySm,
    color: colors.text.tertiary,
  },
  progressSection: {
    marginBottom: spacing.md,
  },
  progressBar: {
    height: 12,
    backgroundColor: colors.bg.tertiary,
    borderRadius: 6,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    backgroundColor: '#4A90D9',
    borderRadius: 6,
  },
  progressFillComplete: {
    backgroundColor: colors.status.success,
  },
  statsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: spacing.xs,
  },
  statsText: {
    ...type.bodySm,
    color: colors.text.secondary,
  },
  statsBold: {
    fontWeight: '700',
    color: colors.text.primary,
  },
  percentText: {
    ...type.bodySm,
    color: '#4A90D9',
    fontWeight: '600',
  },
  percentTextComplete: {
    color: colors.status.success,
  },
  actionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  quickLogBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#4A90D9',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    gap: spacing.xs,
  },
  quickLogText: {
    color: '#fff',
    fontWeight: '600',
    fontSize: 14,
  },
  remainingInfo: {
    flex: 1,
    alignItems: 'flex-end',
  },
  remainingLabel: {
    ...type.caption,
    color: colors.text.tertiary,
    fontSize: 10,
  },
  remainingValue: {
    ...type.h3,
    color: colors.text.primary,
    fontSize: 18,
  },
  goalMetBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    backgroundColor: colors.status.success + '15',
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
  },
  goalMetText: {
    ...type.bodySm,
    color: colors.status.success,
    fontWeight: '600',
  },
});
