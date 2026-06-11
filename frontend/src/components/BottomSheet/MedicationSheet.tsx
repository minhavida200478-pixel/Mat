// Medication logging bottom sheet
import React, { useState, forwardRef, useCallback, useImperativeHandle, useRef } from 'react';
import {
  StyleSheet,
  View,
  Text,
  TouchableOpacity,
  ActivityIndicator,
  Platform,
  TextInput,
  ScrollView,
} from 'react-native';
import BottomSheet, { BottomSheetView, BottomSheetScrollView } from '@gorhom/bottom-sheet';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';

import { colors, radius, spacing, type } from '@/src/theme';
import { api } from '@/src/api/client';

const CATEGORIES = [
  { key: 'painkiller', label: 'Pain Relief', icon: 'bandage-outline' },
  { key: 'vitamin', label: 'Vitamin', icon: 'sunny-outline' },
  { key: 'birth_control', label: 'Birth Control', icon: 'shield-outline' },
  { key: 'hormone', label: 'Hormone', icon: 'fitness-outline' },
  { key: 'supplement', label: 'Supplement', icon: 'leaf-outline' },
  { key: 'other', label: 'Other', icon: 'medical-outline' },
];

export type MedicationSheetRef = {
  open: () => void;
  close: () => void;
};

type Props = {
  onSuccess?: () => void;
};

const MedicationSheet = forwardRef<MedicationSheetRef, Props>(({ onSuccess }, ref) => {
  const bottomSheetRef = useRef<BottomSheet>(null);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [name, setName] = useState('');
  const [dosage, setDosage] = useState('');
  const [category, setCategory] = useState<string | null>(null);

  useImperativeHandle(ref, () => ({
    open: () => {
      setSuccess(false);
      setName('');
      setDosage('');
      setCategory(null);
      bottomSheetRef.current?.expand();
    },
    close: () => bottomSheetRef.current?.close(),
  }));

  const handleLog = useCallback(async () => {
    if (!name.trim()) return;
    if (Platform.OS !== 'web') {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    }
    setLoading(true);
    try {
      await api.post('/medications', {
        name: name.trim(),
        dosage: dosage.trim() || undefined,
        category: category || 'other',
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
      console.error('Failed to log medication:', e);
    } finally {
      setLoading(false);
    }
  }, [name, dosage, category, onSuccess]);

  return (
    <BottomSheet
      ref={bottomSheetRef}
      index={-1}
      snapPoints={[480]}
      enablePanDownToClose
      backgroundStyle={styles.background}
      handleIndicatorStyle={styles.handle}
    >
      <BottomSheetScrollView style={styles.content}>
        <View style={styles.header}>
          <Ionicons name="medical" size={24} color="#9B59B6" />
          <Text style={styles.title}>Log Medication</Text>
        </View>

        {success ? (
          <View style={styles.successContainer}>
            <Ionicons name="checkmark-circle" size={64} color={colors.status.success} />
            <Text style={styles.successText}>{name} logged!</Text>
          </View>
        ) : (
          <>
            <Text style={styles.label}>Medication Name *</Text>
            <TextInput
              style={styles.input}
              placeholder="e.g., Ibuprofen, Vitamin D"
              placeholderTextColor={colors.text.tertiary}
              value={name}
              onChangeText={setName}
            />

            <Text style={styles.label}>Dosage (optional)</Text>
            <TextInput
              style={styles.input}
              placeholder="e.g., 400mg, 1 tablet"
              placeholderTextColor={colors.text.tertiary}
              value={dosage}
              onChangeText={setDosage}
            />

            <Text style={styles.label}>Category</Text>
            <View style={styles.categoriesGrid}>
              {CATEGORIES.map((item) => (
                <TouchableOpacity
                  key={item.key}
                  style={[
                    styles.categoryChip,
                    category === item.key && styles.categoryChipActive,
                  ]}
                  onPress={() => setCategory(item.key)}
                  activeOpacity={0.7}
                >
                  <Ionicons
                    name={item.icon as any}
                    size={16}
                    color={category === item.key ? '#fff' : '#9B59B6'}
                  />
                  <Text
                    style={[
                      styles.categoryLabel,
                      category === item.key && styles.categoryLabelActive,
                    ]}
                  >
                    {item.label}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            <TouchableOpacity
              style={[styles.submitBtn, !name.trim() && styles.submitBtnDisabled]}
              onPress={handleLog}
              disabled={loading || !name.trim()}
              activeOpacity={0.8}
            >
              {loading ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={styles.submitText}>Log Medication</Text>
              )}
            </TouchableOpacity>
          </>
        )}
      </BottomSheetScrollView>
    </BottomSheet>
  );
});

MedicationSheet.displayName = 'MedicationSheet';

export default MedicationSheet;

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
    marginBottom: spacing.xs,
    marginTop: spacing.sm,
  },
  input: {
    ...type.body,
    backgroundColor: colors.bg.secondary,
    borderRadius: radius.sm,
    padding: spacing.md,
    color: colors.text.primary,
    borderWidth: 1,
    borderColor: colors.ui.border,
  },
  categoriesGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    marginTop: spacing.xs,
  },
  categoryChip: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#F3E5F5',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    gap: spacing.xs,
  },
  categoryChipActive: {
    backgroundColor: '#9B59B6',
  },
  categoryLabel: {
    ...type.bodySm,
    color: '#9B59B6',
    fontWeight: '500',
  },
  categoryLabelActive: {
    color: '#fff',
  },
  submitBtn: {
    backgroundColor: '#9B59B6',
    borderRadius: radius.md,
    padding: spacing.md,
    alignItems: 'center',
    marginTop: spacing.lg,
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
