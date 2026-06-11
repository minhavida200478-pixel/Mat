// Meal tracking widget for dashboard
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
  withSpring,
  withSequence,
  withTiming,
} from 'react-native-reanimated';

import { colors, radius, spacing, type } from '@/src/theme';
import { api } from '@/src/api/client';

type MealEntry = {
  id: string;
  status: 'completed' | 'skipped';
  timestamp: string;
  note?: string;
};

type MealSummary = {
  date: string;
  meals: {
    breakfast: MealEntry | null;
    lunch: MealEntry | null;
    dinner: MealEntry | null;
    snack: MealEntry | null;
  };
  completed_count: number;
  skipped_count: number;
};

const MEAL_CONFIG = [
  { key: 'breakfast', label: 'Breakfast', icon: 'sunny-outline', time: '6-10 AM', color: '#FF9800' },
  { key: 'lunch', label: 'Lunch', icon: 'partly-sunny-outline', time: '11-2 PM', color: '#4CAF50' },
  { key: 'dinner', label: 'Dinner', icon: 'moon-outline', time: '5-9 PM', color: '#5C6BC0' },
  { key: 'snack', label: 'Snack', icon: 'nutrition-outline', time: 'Anytime', color: '#E91E63' },
];

type Props = {
  onLogMeal: () => void;
  refreshTrigger?: number;
};

export default function MealWidget({ onLogMeal, refreshTrigger }: Props) {
  const [data, setData] = useState<MealSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [quickLogging, setQuickLogging] = useState<string | null>(null);
  
  const pulseScale = useSharedValue(1);

  const fetchData = useCallback(async () => {
    try {
      const result = await api.get<MealSummary>('/meals/today');
      setData(result);
    } catch (e) {
      console.error('Failed to fetch meal data:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData, refreshTrigger]);

  const handleQuickLog = useCallback(async (mealType: string) => {
    if (Platform.OS !== 'web') {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    }
    setQuickLogging(mealType);
    
    // Pulse animation
    pulseScale.value = withSequence(
      withSpring(1.1, { damping: 10 }),
      withSpring(1)
    );
    
    try {
      await api.post('/meals', { meal_type: mealType });
      if (Platform.OS !== 'web') {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      }
      fetchData();
    } catch (e) {
      console.error('Failed to quick log meal:', e);
    } finally {
      setQuickLogging(null);
    }
  }, [fetchData, pulseScale]);

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

  const completedCount = data?.completed_count ?? 0;
  const totalMeals = 4;
  const percentage = Math.round((completedCount / totalMeals) * 100);

  // Determine next suggested meal based on time
  const hour = new Date().getHours();
  let suggestedMeal = 'snack';
  if (hour >= 6 && hour < 11) suggestedMeal = 'breakfast';
  else if (hour >= 11 && hour < 15) suggestedMeal = 'lunch';
  else if (hour >= 17 && hour < 21) suggestedMeal = 'dinner';

  const suggestedConfig = MEAL_CONFIG.find(m => m.key === suggestedMeal);
  const isSuggestedLogged = data?.meals[suggestedMeal as keyof typeof data.meals] !== null;

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <View style={styles.titleRow}>
          <Ionicons name="restaurant" size={20} color="#E67E22" />
          <Text style={styles.title}>Meals</Text>
        </View>
        <TouchableOpacity
          onPress={onLogMeal}
          style={styles.moreBtn}
          activeOpacity={0.7}
        >
          <Text style={styles.moreBtnText}>Details</Text>
          <Ionicons name="chevron-forward" size={16} color={colors.text.tertiary} />
        </TouchableOpacity>
      </View>

      {/* Meal Status Grid */}
      <View style={styles.mealsGrid}>
        {MEAL_CONFIG.map((meal) => {
          const isLogged = data?.meals[meal.key as keyof typeof data.meals] !== null;
          const isLogging = quickLogging === meal.key;
          
          return (
            <TouchableOpacity
              key={meal.key}
              style={[
                styles.mealItem,
                isLogged && styles.mealItemLogged,
              ]}
              onPress={() => !isLogged && handleQuickLog(meal.key)}
              disabled={isLogged || isLogging}
              activeOpacity={0.7}
            >
              <View style={[styles.mealIconWrap, { backgroundColor: meal.color + '15' }]}>
                {isLogging ? (
                  <ActivityIndicator color={meal.color} size="small" />
                ) : (
                  <Ionicons 
                    name={isLogged ? 'checkmark-circle' : meal.icon as any} 
                    size={20} 
                    color={isLogged ? colors.status.success : meal.color} 
                  />
                )}
              </View>
              <Text style={[
                styles.mealLabel,
                isLogged && styles.mealLabelLogged
              ]}>{meal.label}</Text>
            </TouchableOpacity>
          );
        })}
      </View>

      {/* Summary Row */}
      <View style={styles.summaryRow}>
        <View style={styles.progressInfo}>
          <Text style={styles.progressText}>
            <Text style={styles.progressBold}>{completedCount}</Text> of {totalMeals} meals logged
          </Text>
          <View style={styles.progressBar}>
            <View style={[styles.progressFill, { width: `${percentage}%` }]} />
          </View>
        </View>

        {!isSuggestedLogged && suggestedConfig && (
          <TouchableOpacity
            style={[styles.suggestBtn, { backgroundColor: suggestedConfig.color }]}
            onPress={() => handleQuickLog(suggestedMeal)}
            disabled={quickLogging !== null}
            activeOpacity={0.7}
          >
            <Animated.View style={animatedIconStyle}>
              {quickLogging === suggestedMeal ? (
                <ActivityIndicator color="#fff" size="small" />
              ) : (
                <Ionicons name="add" size={18} color="#fff" />
              )}
            </Animated.View>
            <Text style={styles.suggestBtnText}>{suggestedConfig.label}</Text>
          </TouchableOpacity>
        )}

        {completedCount === totalMeals && (
          <View style={styles.allDoneBadge}>
            <Ionicons name="checkmark-circle" size={16} color={colors.status.success} />
            <Text style={styles.allDoneText}>All meals logged!</Text>
          </View>
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
    minHeight: 160,
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
  mealsGrid: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: spacing.md,
  },
  mealItem: {
    alignItems: 'center',
    flex: 1,
    paddingVertical: spacing.sm,
  },
  mealItemLogged: {
    opacity: 0.7,
  },
  mealIconWrap: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.xs,
  },
  mealLabel: {
    ...type.caption,
    color: colors.text.secondary,
    fontSize: 10,
    textTransform: 'none',
  },
  mealLabelLogged: {
    color: colors.status.success,
  },
  summaryRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.ui.divider,
    paddingTop: spacing.md,
  },
  progressInfo: {
    flex: 1,
  },
  progressText: {
    ...type.bodySm,
    color: colors.text.secondary,
    marginBottom: spacing.xs,
  },
  progressBold: {
    fontWeight: '700',
    color: colors.text.primary,
  },
  progressBar: {
    height: 6,
    backgroundColor: colors.bg.tertiary,
    borderRadius: 3,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    backgroundColor: '#E67E22',
    borderRadius: 3,
  },
  suggestBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    gap: spacing.xs,
  },
  suggestBtnText: {
    color: '#fff',
    fontWeight: '600',
    fontSize: 13,
  },
  allDoneBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    backgroundColor: colors.status.success + '15',
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
  },
  allDoneText: {
    ...type.bodySm,
    color: colors.status.success,
    fontWeight: '600',
    fontSize: 12,
  },
});
