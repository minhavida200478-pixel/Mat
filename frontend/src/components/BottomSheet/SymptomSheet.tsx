// Symptom logging bottom sheet
import React, { useState, forwardRef, useCallback, useImperativeHandle, useRef } from 'react';
import {
  StyleSheet,
  View,
  Text,
  TouchableOpacity,
  ActivityIndicator,
  Platform,
  ScrollView,
} from 'react-native';
import BottomSheet, { BottomSheetScrollView } from '@gorhom/bottom-sheet';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';

import { colors, radius, spacing, type } from '@/src/theme';
import { api } from '@/src/api/client';

const SYMPTOMS = [
  { name: 'Cramps', icon: 'flash-outline' },
  { name: 'Headache', icon: 'alert-circle-outline' },
  { name: 'Bloating', icon: 'water-outline' },
  { name: 'Fatigue', icon: 'bed-outline' },
  { name: 'Back Pain', icon: 'body-outline' },
  { name: 'Breast Tenderness', icon: 'heart-outline' },
  { name: 'Nausea', icon: 'sad-outline' },
  { name: 'Acne', icon: 'ellipse-outline' },
  { name: 'Insomnia', icon: 'moon-outline' },
  { name: 'Cravings', icon: 'fast-food-outline' },
];

const SEVERITIES = [
  { level: 'mild', label: 'Mild', color: '#4CAF50' },
  { level: 'moderate', label: 'Moderate', color: '#FF9800' },
  { level: 'severe', label: 'Severe', color: '#F44336' },
];

export type SymptomSheetRef = {
  open: () => void;
  close: () => void;
};

type Props = {
  onSuccess?: () => void;
};

const SymptomSheet = forwardRef<SymptomSheetRef, Props>(({ onSuccess }, ref) => {
  const bottomSheetRef = useRef<BottomSheet>(null);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [selectedSymptom, setSelectedSymptom] = useState<string | null>(null);
  const [selectedSeverity, setSelectedSeverity] = useState<string>('moderate');

  useImperativeHandle(ref, () => ({
    open: () => {
      setSuccess(false);
      setSelectedSymptom(null);
      setSelectedSeverity('moderate');
      bottomSheetRef.current?.expand();
    },
    close: () => bottomSheetRef.current?.close(),
  }));

  const handleLog = useCallback(async () => {
    if (!selectedSymptom) return;
    if (Platform.OS !== 'web') {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    }
    setLoading(true);
    try {
      await api.post('/health-events', {
        event_type: 'symptom',
        data: {
          name: selectedSymptom,
          severity: selectedSeverity,
        },
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
      console.error('Failed to log symptom:', e);
    } finally {
      setLoading(false);
    }
  }, [selectedSymptom, selectedSeverity, onSuccess]);

  return (
    <BottomSheet
      ref={bottomSheetRef}
      index={-1}
      snapPoints={[520]}
      enablePanDownToClose
      backgroundStyle={styles.background}
      handleIndicatorStyle={styles.handle}
    >
      <BottomSheetScrollView style={styles.content}>
        <View style={styles.header}>
          <Ionicons name="pulse" size={24} color={colors.brand.primary} />
          <Text style={styles.title}>Log Symptom</Text>
        </View>

        {success ? (
          <View style={styles.successContainer}>
            <Ionicons name="checkmark-circle" size={64} color={colors.status.success} />
            <Text style={styles.successText}>{selectedSymptom} logged!</Text>
          </View>
        ) : (
          <>
            <Text style={styles.label}>Select symptom</Text>
            <View style={styles.symptomsGrid}>
              {SYMPTOMS.map((item) => (
                <TouchableOpacity
                  key={item.name}
                  style={[
                    styles.symptomChip,
                    selectedSymptom === item.name && styles.symptomChipActive,
                  ]}
                  onPress={() => setSelectedSymptom(item.name)}
                  activeOpacity={0.7}
                >
                  <Ionicons
                    name={item.icon as any}
                    size={16}
                    color={selectedSymptom === item.name ? '#fff' : colors.brand.primary}
                  />
                  <Text
                    style={[
                      styles.symptomLabel,
                      selectedSymptom === item.name && styles.symptomLabelActive,
                    ]}
                  >
                    {item.name}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            <Text style={styles.label}>Severity</Text>
            <View style={styles.severityRow}>
              {SEVERITIES.map((item) => (
                <TouchableOpacity
                  key={item.level}
                  style={[
                    styles.severityBtn,
                    selectedSeverity === item.level && { backgroundColor: item.color },
                  ]}
                  onPress={() => setSelectedSeverity(item.level)}
                  activeOpacity={0.7}
                >
                  <Text
                    style={[
                      styles.severityLabel,
                      selectedSeverity === item.level && styles.severityLabelActive,
                    ]}
                  >
                    {item.label}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            <TouchableOpacity
              style={[styles.submitBtn, !selectedSymptom && styles.submitBtnDisabled]}
              onPress={handleLog}
              disabled={loading || !selectedSymptom}
              activeOpacity={0.8}
            >
              {loading ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={styles.submitText}>Log Symptom</Text>
              )}
            </TouchableOpacity>
          </>
        )}
      </BottomSheetScrollView>
    </BottomSheet>
  );
});

SymptomSheet.displayName = 'SymptomSheet';

export default SymptomSheet;

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
  label: {
    ...type.bodySm,
    color: colors.text.secondary,
    fontWeight: '600',
    marginBottom: spacing.sm,
    marginTop: spacing.md,
  },
  symptomsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  symptomChip: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.brand.primaryLight,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    gap: spacing.xs,
  },
  symptomChipActive: {
    backgroundColor: colors.brand.primary,
  },
  symptomLabel: {
    ...type.bodySm,
    color: colors.brand.primary,
    fontWeight: '500',
  },
  symptomLabelActive: {
    color: '#fff',
  },
  severityRow: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  severityBtn: {
    flex: 1,
    backgroundColor: colors.bg.secondary,
    borderRadius: radius.md,
    padding: spacing.md,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.ui.border,
  },
  severityLabel: {
    ...type.body,
    color: colors.text.secondary,
    fontWeight: '600',
  },
  severityLabelActive: {
    color: '#fff',
  },
  submitBtn: {
    backgroundColor: colors.brand.primary,
    borderRadius: radius.md,
    padding: spacing.md,
    alignItems: 'center',
    marginTop: spacing.xl,
    marginBottom: spacing.lg,
  },
  submitBtnDisabled: {
    opacity: 0.5,
  },
  submitText: {
    ...type.body,
    color: '#fff',
    fontWeight: '600',
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
