// Enhanced Water logging bottom sheet with custom amounts and beverage types
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

const BEVERAGE_TYPES = [
  { id: 'water', label: 'Water', icon: 'water', color: '#4A90D9' },
  { id: 'coffee', label: 'Coffee', icon: 'cafe', color: '#795548' },
  { id: 'tea', label: 'Tea', icon: 'leaf', color: '#4CAF50' },
  { id: 'juice', label: 'Juice', icon: 'nutrition', color: '#FF9800' },
  { id: 'milk', label: 'Milk', icon: 'water', color: '#E0E0E0' },
  { id: 'smoothie', label: 'Smoothie', icon: 'color-fill', color: '#E91E63' },
];

const QUICK_AMOUNTS = [
  { ml: 150, label: '150ml', sublabel: 'Small cup' },
  { ml: 250, label: '250ml', sublabel: 'Glass' },
  { ml: 350, label: '350ml', sublabel: 'Mug' },
  { ml: 500, label: '500ml', sublabel: 'Bottle' },
  { ml: 750, label: '750ml', sublabel: 'Large' },
  { ml: 1000, label: '1000ml', sublabel: '1 Liter' },
];

export type WaterSheetRef = {
  open: () => void;
  close: () => void;
};

type Props = {
  onSuccess?: () => void;
};

const WaterSheet = forwardRef<WaterSheetRef, Props>(({ onSuccess }, ref) => {
  const bottomSheetRef = useRef<BottomSheet>(null);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [selectedBeverage, setSelectedBeverage] = useState('water');
  const [selectedAmount, setSelectedAmount] = useState<number | null>(null);
  const [customAmount, setCustomAmount] = useState('');
  const [showCustomInput, setShowCustomInput] = useState(false);

  useImperativeHandle(ref, () => ({
    open: () => {
      setSuccess(false);
      setSelectedAmount(null);
      setSelectedBeverage('water');
      setCustomAmount('');
      setShowCustomInput(false);
      bottomSheetRef.current?.expand();
    },
    close: () => bottomSheetRef.current?.close(),
  }));

  const triggerHaptic = useCallback((style: 'light' | 'medium' | 'success') => {
    if (Platform.OS !== 'web') {
      if (style === 'success') {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      } else {
        Haptics.impactAsync(
          style === 'light' 
            ? Haptics.ImpactFeedbackStyle.Light 
            : Haptics.ImpactFeedbackStyle.Medium
        );
      }
    }
  }, []);

  const handleLog = useCallback(async (amount_ml: number) => {
    triggerHaptic('light');
    setSelectedAmount(amount_ml);
    setLoading(true);
    try {
      const beverage = BEVERAGE_TYPES.find(b => b.id === selectedBeverage);
      await api.post('/water', { 
        amount_ml,
        note: beverage?.id !== 'water' ? beverage?.label : undefined
      });
      setSuccess(true);
      triggerHaptic('success');
      setTimeout(() => {
        bottomSheetRef.current?.close();
        onSuccess?.();
      }, 800);
    } catch (e) {
      console.error('Failed to log water:', e);
    } finally {
      setLoading(false);
    }
  }, [onSuccess, selectedBeverage, triggerHaptic]);

  const handleCustomSubmit = useCallback(() => {
    const amount = parseInt(customAmount, 10);
    if (amount > 0 && amount <= 5000) {
      handleLog(amount);
    }
  }, [customAmount, handleLog]);

  const selectedBeverageData = BEVERAGE_TYPES.find(b => b.id === selectedBeverage) || BEVERAGE_TYPES[0];

  return (
    <BottomSheet
      ref={bottomSheetRef}
      index={-1}
      snapPoints={[520]}
      enablePanDownToClose
      backgroundStyle={styles.background}
      handleIndicatorStyle={styles.handle}
    >
      <BottomSheetScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.header}>
          <Ionicons name="water" size={24} color="#4A90D9" />
          <Text style={styles.title}>Log Hydration</Text>
        </View>

        {success ? (
          <View style={styles.successContainer}>
            <Ionicons name="checkmark-circle" size={64} color={colors.status.success} />
            <Text style={styles.successText}>+{selectedAmount}ml logged!</Text>
            <Text style={styles.successSubtext}>{selectedBeverageData.label}</Text>
          </View>
        ) : (
          <>
            {/* Beverage Type Selection */}
            <Text style={styles.sectionLabel}>BEVERAGE TYPE</Text>
            <ScrollView 
              horizontal 
              showsHorizontalScrollIndicator={false}
              style={styles.beverageScroll}
              contentContainerStyle={styles.beverageContainer}
            >
              {BEVERAGE_TYPES.map((item) => (
                <TouchableOpacity
                  key={item.id}
                  style={[
                    styles.beverageCard,
                    selectedBeverage === item.id && { borderColor: item.color, backgroundColor: item.color + '15' },
                  ]}
                  onPress={() => {
                    triggerHaptic('light');
                    setSelectedBeverage(item.id);
                  }}
                  activeOpacity={0.7}
                >
                  <Ionicons name={item.icon as any} size={24} color={item.color} />
                  <Text style={[
                    styles.beverageLabel,
                    selectedBeverage === item.id && { color: item.color, fontWeight: '600' }
                  ]}>{item.label}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>

            {/* Amount Selection */}
            <Text style={styles.sectionLabel}>AMOUNT</Text>
            <View style={styles.amountsGrid}>
              {QUICK_AMOUNTS.map((item) => (
                <TouchableOpacity
                  key={item.ml}
                  style={[
                    styles.amountCard,
                    selectedAmount === item.ml && loading && styles.amountCardActive,
                  ]}
                  onPress={() => handleLog(item.ml)}
                  disabled={loading}
                  activeOpacity={0.7}
                >
                  {loading && selectedAmount === item.ml ? (
                    <ActivityIndicator color={colors.brand.primary} />
                  ) : (
                    <>
                      <Text style={styles.amountValue}>{item.label}</Text>
                      <Text style={styles.amountSublabel}>{item.sublabel}</Text>
                    </>
                  )}
                </TouchableOpacity>
              ))}
            </View>

            {/* Custom Amount */}
            <TouchableOpacity
              style={styles.customToggle}
              onPress={() => setShowCustomInput(!showCustomInput)}
              activeOpacity={0.7}
            >
              <Ionicons 
                name={showCustomInput ? 'chevron-up' : 'chevron-down'} 
                size={20} 
                color={colors.text.secondary} 
              />
              <Text style={styles.customToggleText}>Custom amount</Text>
            </TouchableOpacity>

            {showCustomInput && (
              <View style={styles.customInputContainer}>
                <View style={styles.customInputRow}>
                  <TextInput
                    style={styles.customInput}
                    value={customAmount}
                    onChangeText={setCustomAmount}
                    placeholder="Enter ml"
                    placeholderTextColor={colors.text.tertiary}
                    keyboardType="numeric"
                    maxLength={4}
                  />
                  <Text style={styles.mlLabel}>ml</Text>
                </View>
                <TouchableOpacity
                  style={[
                    styles.customSubmitBtn,
                    (!customAmount || parseInt(customAmount) <= 0) && styles.customSubmitBtnDisabled
                  ]}
                  onPress={handleCustomSubmit}
                  disabled={!customAmount || parseInt(customAmount) <= 0 || loading}
                  activeOpacity={0.7}
                >
                  {loading && selectedAmount === parseInt(customAmount) ? (
                    <ActivityIndicator color="#fff" size="small" />
                  ) : (
                    <Text style={styles.customSubmitText}>Log</Text>
                  )}
                </TouchableOpacity>
              </View>
            )}
          </>
        )}
      </BottomSheetScrollView>
    </BottomSheet>
  );
});

WaterSheet.displayName = 'WaterSheet';

export default WaterSheet;

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
  sectionLabel: {
    ...type.caption,
    color: colors.text.tertiary,
    marginTop: spacing.md,
    marginBottom: spacing.sm,
  },
  beverageScroll: {
    marginHorizontal: -spacing.screen,
  },
  beverageContainer: {
    paddingHorizontal: spacing.screen,
    gap: spacing.sm,
  },
  beverageCard: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    backgroundColor: colors.bg.secondary,
    borderWidth: 2,
    borderColor: 'transparent',
    alignItems: 'center',
    flexDirection: 'row',
    gap: spacing.xs,
  },
  beverageLabel: {
    ...type.bodySm,
    color: colors.text.secondary,
  },
  amountsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  amountCard: {
    width: '31%',
    backgroundColor: colors.bg.secondary,
    borderRadius: radius.md,
    padding: spacing.md,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.ui.border,
    minHeight: 70,
    justifyContent: 'center',
  },
  amountCardActive: {
    borderColor: colors.brand.primary,
    backgroundColor: colors.brand.primaryLight,
  },
  amountValue: {
    ...type.h3,
    color: colors.text.primary,
    fontSize: 18,
  },
  amountSublabel: {
    ...type.bodySm,
    color: colors.text.tertiary,
    fontSize: 11,
    marginTop: 2,
  },
  customToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.md,
    marginTop: spacing.sm,
  },
  customToggleText: {
    ...type.bodySm,
    color: colors.text.secondary,
    marginLeft: spacing.xs,
  },
  customInputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.lg,
  },
  customInputRow: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.bg.secondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.ui.border,
    paddingHorizontal: spacing.md,
  },
  customInput: {
    flex: 1,
    height: 48,
    fontSize: 18,
    color: colors.text.primary,
  },
  mlLabel: {
    ...type.body,
    color: colors.text.tertiary,
  },
  customSubmitBtn: {
    backgroundColor: colors.brand.primary,
    paddingHorizontal: spacing.lg,
    height: 48,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  customSubmitBtnDisabled: {
    opacity: 0.5,
  },
  customSubmitText: {
    color: '#fff',
    fontWeight: '600',
    fontSize: 16,
  },
  successContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.xxl,
  },
  successText: {
    ...type.h2,
    color: colors.status.success,
    marginTop: spacing.md,
  },
  successSubtext: {
    ...type.body,
    color: colors.text.secondary,
    marginTop: spacing.xs,
  },
});
