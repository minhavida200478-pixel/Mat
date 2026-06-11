// Mood logging bottom sheet
import React, { useState, forwardRef, useCallback, useImperativeHandle, useRef } from 'react';
import {
  StyleSheet,
  View,
  Text,
  TouchableOpacity,
  ActivityIndicator,
  Platform,
} from 'react-native';
import BottomSheet, { BottomSheetView } from '@gorhom/bottom-sheet';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';

import { colors, radius, spacing, type } from '@/src/theme';
import { api } from '@/src/api/client';

const MOODS = [
  { name: 'Happy', icon: 'happy', color: '#4CAF50' },
  { name: 'Calm', icon: 'leaf', color: '#2196F3' },
  { name: 'Energetic', icon: 'flash', color: '#FF9800' },
  { name: 'Tired', icon: 'bed', color: '#9E9E9E' },
  { name: 'Anxious', icon: 'alert-circle', color: '#9C27B0' },
  { name: 'Irritable', icon: 'thunderstorm', color: '#F44336' },
  { name: 'Sad', icon: 'sad', color: '#607D8B' },
  { name: 'Sensitive', icon: 'heart', color: '#E91E63' },
];

export type MoodSheetRef = {
  open: () => void;
  close: () => void;
};

type Props = {
  onSuccess?: () => void;
};

const MoodSheet = forwardRef<MoodSheetRef, Props>(({ onSuccess }, ref) => {
  const bottomSheetRef = useRef<BottomSheet>(null);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [selectedMood, setSelectedMood] = useState<string | null>(null);

  useImperativeHandle(ref, () => ({
    open: () => {
      setSuccess(false);
      setSelectedMood(null);
      bottomSheetRef.current?.expand();
    },
    close: () => bottomSheetRef.current?.close(),
  }));

  const handleLog = useCallback(async (mood: string) => {
    if (Platform.OS !== 'web') {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    }
    setSelectedMood(mood);
    setLoading(true);
    try {
      await api.post('/health-events', {
        event_type: 'mood',
        data: { name: mood },
      });
      setSuccess(true);
      if (Platform.OS !== 'web') {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      }
      setTimeout(() => {
        bottomSheetRef.current?.close();
        onSuccess?.();
      }, 800);
    } catch (e) {
      console.error('Failed to log mood:', e);
    } finally {
      setLoading(false);
    }
  }, [onSuccess]);

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
          <Ionicons name="happy" size={24} color={colors.status.fertile} />
          <Text style={styles.title}>How are you feeling?</Text>
        </View>

        {success ? (
          <View style={styles.successContainer}>
            <Ionicons name="checkmark-circle" size={64} color={colors.status.success} />
            <Text style={styles.successText}>{selectedMood} logged!</Text>
          </View>
        ) : (
          <View style={styles.moodsGrid}>
            {MOODS.map((item) => (
              <TouchableOpacity
                key={item.name}
                style={[
                  styles.moodCard,
                  selectedMood === item.name && loading && { borderColor: item.color },
                ]}
                onPress={() => handleLog(item.name)}
                disabled={loading}
                activeOpacity={0.7}
              >
                {loading && selectedMood === item.name ? (
                  <ActivityIndicator color={item.color} />
                ) : (
                  <>
                    <Ionicons name={item.icon as any} size={32} color={item.color} />
                    <Text style={styles.moodLabel}>{item.name}</Text>
                  </>
                )}
              </TouchableOpacity>
            ))}
          </View>
        )}
      </BottomSheetView>
    </BottomSheet>
  );
});

MoodSheet.displayName = 'MoodSheet';

export default MoodSheet;

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
    marginBottom: spacing.lg,
  },
  title: {
    ...type.h3,
    color: colors.text.primary,
    marginLeft: spacing.sm,
  },
  moodsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.md,
  },
  moodCard: {
    width: '22%',
    aspectRatio: 1,
    backgroundColor: colors.bg.secondary,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    borderColor: 'transparent',
  },
  moodLabel: {
    ...type.bodySm,
    color: colors.text.primary,
    marginTop: spacing.xs,
    fontSize: 11,
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
  },
});
