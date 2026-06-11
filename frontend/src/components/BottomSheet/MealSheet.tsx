// Meal logging bottom sheet
import React, { useState, forwardRef, useCallback, useImperativeHandle, useRef } from 'react';
import {
  StyleSheet,
  View,
  Text,
  TouchableOpacity,
  ActivityIndicator,
  Platform,
  TextInput,
} from 'react-native';
import BottomSheet, { BottomSheetView } from '@gorhom/bottom-sheet';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';

import { colors, radius, spacing, type } from '@/src/theme';
import { api } from '@/src/api/client';

const MEAL_TYPES = [
  { type: 'breakfast', label: 'Breakfast', icon: 'sunny-outline', time: '6-10 AM' },
  { type: 'lunch', label: 'Lunch', icon: 'partly-sunny-outline', time: '11 AM-2 PM' },
  { type: 'dinner', label: 'Dinner', icon: 'moon-outline', time: '5-9 PM' },
  { type: 'snack', label: 'Snack', icon: 'nutrition-outline', time: 'Anytime' },
];

export type MealSheetRef = {
  open: () => void;
  close: () => void;
};

type Props = {
  onSuccess?: () => void;
};

const MealSheet = forwardRef<MealSheetRef, Props>(({ onSuccess }, ref) => {
  const bottomSheetRef = useRef<BottomSheet>(null);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [selectedMeal, setSelectedMeal] = useState<string | null>(null);
  const [note, setNote] = useState('');

  useImperativeHandle(ref, () => ({
    open: () => {
      setSuccess(false);
      setSelectedMeal(null);
      setNote('');
      bottomSheetRef.current?.expand();
    },
    close: () => bottomSheetRef.current?.close(),
  }));

  const handleLog = useCallback(async (meal_type: string) => {
    if (Platform.OS !== 'web') {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    }
    setSelectedMeal(meal_type);
    setLoading(true);
    try {
      await api.post('/meals', { meal_type, note: note || undefined });
      setSuccess(true);
      if (Platform.OS !== 'web') {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      }
      setTimeout(() => {
        bottomSheetRef.current?.close();
        onSuccess?.();
      }, 800);
    } catch (e) {
      console.error('Failed to log meal:', e);
    } finally {
      setLoading(false);
    }
  }, [note, onSuccess]);

  return (
    <BottomSheet
      ref={bottomSheetRef}
      index={-1}
      snapPoints={[380]}
      enablePanDownToClose
      backgroundStyle={styles.background}
      handleIndicatorStyle={styles.handle}
    >
      <BottomSheetView style={styles.content}>
        <View style={styles.header}>
          <Ionicons name="restaurant" size={24} color="#E67E22" />
          <Text style={styles.title}>Log Meal</Text>
        </View>

        {success ? (
          <View style={styles.successContainer}>
            <Ionicons name="checkmark-circle" size={64} color={colors.status.success} />
            <Text style={styles.successText}>{selectedMeal} logged!</Text>
          </View>
        ) : (
          <>
            <TextInput
              style={styles.noteInput}
              placeholder="Add a note (optional)"
              placeholderTextColor={colors.text.tertiary}
              value={note}
              onChangeText={setNote}
            />
            <View style={styles.optionsGrid}>
              {MEAL_TYPES.map((item) => (
                <TouchableOpacity
                  key={item.type}
                  style={[
                    styles.optionCard,
                    selectedMeal === item.type && loading && styles.optionCardActive,
                  ]}
                  onPress={() => handleLog(item.type)}
                  disabled={loading}
                  activeOpacity={0.7}
                >
                  {loading && selectedMeal === item.type ? (
                    <ActivityIndicator color={colors.brand.primary} />
                  ) : (
                    <>
                      <Ionicons name={item.icon as any} size={28} color="#E67E22" />
                      <Text style={styles.optionLabel}>{item.label}</Text>
                      <Text style={styles.optionTime}>{item.time}</Text>
                    </>
                  )}
                </TouchableOpacity>
              ))}
            </View>
          </>
        )}
      </BottomSheetView>
    </BottomSheet>
  );
});

MealSheet.displayName = 'MealSheet';

export default MealSheet;

const styles = StyleSheet.create({
  background: {
    backgroundColor: colors.bg.primary,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
  },
  handle: {
    backgroundColor: colors.ui.border,
    width: 40,
  },
  content: {
    flex: 1,
    paddingHorizontal: spacing.screen,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  title: {
    ...type.h3,
    color: colors.text.primary,
    marginLeft: spacing.sm,
  },
  noteInput: {
    ...type.body,
    backgroundColor: colors.bg.secondary,
    borderRadius: radius.sm,
    padding: spacing.md,
    marginBottom: spacing.md,
    color: colors.text.primary,
  },
  optionsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.md,
  },
  optionCard: {
    width: '47%',
    backgroundColor: colors.bg.secondary,
    borderRadius: radius.md,
    padding: spacing.md,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.ui.border,
  },
  optionCardActive: {
    borderColor: '#E67E22',
    backgroundColor: '#FDF2E6',
  },
  optionLabel: {
    ...type.body,
    color: colors.text.primary,
    fontWeight: '600',
    marginTop: spacing.xs,
  },
  optionTime: {
    ...type.bodySm,
    color: colors.text.tertiary,
  },
  successContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.xl,
  },
  successText: {
    ...type.h2,
    color: colors.status.success,
    marginTop: spacing.md,
    textTransform: 'capitalize',
  },
});
