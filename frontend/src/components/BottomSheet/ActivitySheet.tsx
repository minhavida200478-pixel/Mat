// Sexual activity logging bottom sheet
import React, { useState, forwardRef, useCallback, useImperativeHandle, useRef } from 'react';
import {
  StyleSheet,
  View,
  Text,
  TouchableOpacity,
  ActivityIndicator,
  Platform,
  TextInput,
  Switch,
} from 'react-native';
import BottomSheet, { BottomSheetView } from '@gorhom/bottom-sheet';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';

import { colors, radius, spacing, type } from '@/src/theme';
import { api } from '@/src/api/client';

export type ActivitySheetRef = {
  open: () => void;
  close: () => void;
};

type Props = {
  onSuccess?: () => void;
};

const ActivitySheet = forwardRef<ActivitySheetRef, Props>(({ onSuccess }, ref) => {
  const bottomSheetRef = useRef<BottomSheet>(null);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [protectionUsed, setProtectionUsed] = useState(false);
  const [partnerPresent, setPartnerPresent] = useState(true);
  const [note, setNote] = useState('');

  useImperativeHandle(ref, () => ({
    open: () => {
      setSuccess(false);
      setProtectionUsed(false);
      setPartnerPresent(true);
      setNote('');
      bottomSheetRef.current?.expand();
    },
    close: () => bottomSheetRef.current?.close(),
  }));

  const handleLog = useCallback(async () => {
    if (Platform.OS !== 'web') {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    }
    setLoading(true);
    try {
      await api.post('/sexual-activity', {
        protection_used: protectionUsed,
        partner_present: partnerPresent,
        note: note.trim() || undefined,
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
      console.error('Failed to log activity:', e);
    } finally {
      setLoading(false);
    }
  }, [protectionUsed, partnerPresent, note, onSuccess]);

  return (
    <BottomSheet
      ref={bottomSheetRef}
      index={-1}
      snapPoints={[400]}
      enablePanDownToClose
      backgroundStyle={styles.background}
      handleIndicatorStyle={styles.handle}
    >
      <BottomSheetView style={styles.content}>
        <View style={styles.header}>
          <Ionicons name="heart" size={24} color="#E91E63" />
          <Text style={styles.title}>Log Activity</Text>
        </View>

        {success ? (
          <View style={styles.successContainer}>
            <Ionicons name="checkmark-circle" size={64} color={colors.status.success} />
            <Text style={styles.successText}>Activity logged!</Text>
          </View>
        ) : (
          <>
            <View style={styles.row}>
              <View style={styles.rowContent}>
                <Ionicons name="shield-checkmark-outline" size={22} color="#E91E63" />
                <Text style={styles.rowLabel}>Protection used</Text>
              </View>
              <Switch
                value={protectionUsed}
                onValueChange={setProtectionUsed}
                trackColor={{ false: colors.ui.border, true: '#F8BBD9' }}
                thumbColor={protectionUsed ? '#E91E63' : colors.text.tertiary}
              />
            </View>

            <View style={styles.row}>
              <View style={styles.rowContent}>
                <Ionicons name="people-outline" size={22} color="#E91E63" />
                <Text style={styles.rowLabel}>Partner present</Text>
              </View>
              <Switch
                value={partnerPresent}
                onValueChange={setPartnerPresent}
                trackColor={{ false: colors.ui.border, true: '#F8BBD9' }}
                thumbColor={partnerPresent ? '#E91E63' : colors.text.tertiary}
              />
            </View>

            <Text style={styles.label}>Private note (optional)</Text>
            <TextInput
              style={styles.input}
              placeholder="Add a private note..."
              placeholderTextColor={colors.text.tertiary}
              value={note}
              onChangeText={setNote}
              multiline
              numberOfLines={2}
            />

            <Text style={styles.privacyNote}>
              <Ionicons name="lock-closed" size={12} color={colors.text.tertiary} />
              {' This data is private and not shared with partners'}
            </Text>

            <TouchableOpacity
              style={styles.submitBtn}
              onPress={handleLog}
              disabled={loading}
              activeOpacity={0.8}
            >
              {loading ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={styles.submitText}>Log Activity</Text>
              )}
            </TouchableOpacity>
          </>
        )}
      </BottomSheetView>
    </BottomSheet>
  );
});

ActivitySheet.displayName = 'ActivitySheet';

export default ActivitySheet;

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
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.ui.divider,
  },
  rowContent: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  rowLabel: {
    ...type.body,
    color: colors.text.primary,
  },
  label: {
    ...type.bodySm,
    color: colors.text.secondary,
    fontWeight: '600',
    marginTop: spacing.md,
    marginBottom: spacing.xs,
  },
  input: {
    ...type.body,
    backgroundColor: colors.bg.secondary,
    borderRadius: radius.sm,
    padding: spacing.md,
    color: colors.text.primary,
    borderWidth: 1,
    borderColor: colors.ui.border,
    minHeight: 60,
    textAlignVertical: 'top',
  },
  privacyNote: {
    ...type.bodySm,
    color: colors.text.tertiary,
    marginTop: spacing.sm,
  },
  submitBtn: {
    backgroundColor: '#E91E63',
    borderRadius: radius.md,
    padding: spacing.md,
    alignItems: 'center',
    marginTop: spacing.lg,
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
