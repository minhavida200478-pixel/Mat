// Note logging bottom sheet
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

export type NoteSheetRef = {
  open: () => void;
  close: () => void;
};

type Props = {
  onSuccess?: () => void;
};

const NoteSheet = forwardRef<NoteSheetRef, Props>(({ onSuccess }, ref) => {
  const bottomSheetRef = useRef<BottomSheet>(null);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [note, setNote] = useState('');

  useImperativeHandle(ref, () => ({
    open: () => {
      setSuccess(false);
      setNote('');
      bottomSheetRef.current?.expand();
    },
    close: () => bottomSheetRef.current?.close(),
  }));

  const handleLog = useCallback(async () => {
    if (!note.trim()) return;
    if (Platform.OS !== 'web') {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    }
    setLoading(true);
    try {
      await api.post('/health-events', {
        event_type: 'note',
        note: note.trim(),
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
      console.error('Failed to log note:', e);
    } finally {
      setLoading(false);
    }
  }, [note, onSuccess]);

  return (
    <BottomSheet
      ref={bottomSheetRef}
      index={-1}
      snapPoints={[320]}
      enablePanDownToClose
      backgroundStyle={styles.background}
      handleIndicatorStyle={styles.handle}
    >
      <BottomSheetView style={styles.content}>
        <View style={styles.header}>
          <Ionicons name="create" size={24} color="#607D8B" />
          <Text style={styles.title}>Add Note</Text>
        </View>

        {success ? (
          <View style={styles.successContainer}>
            <Ionicons name="checkmark-circle" size={64} color={colors.status.success} />
            <Text style={styles.successText}>Note saved!</Text>
          </View>
        ) : (
          <>
            <TextInput
              style={styles.input}
              placeholder="Write your note here..."
              placeholderTextColor={colors.text.tertiary}
              value={note}
              onChangeText={setNote}
              multiline
              numberOfLines={4}
              autoFocus
            />

            <TouchableOpacity
              style={[styles.submitBtn, !note.trim() && styles.submitBtnDisabled]}
              onPress={handleLog}
              disabled={loading || !note.trim()}
              activeOpacity={0.8}
            >
              {loading ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={styles.submitText}>Save Note</Text>
              )}
            </TouchableOpacity>
          </>
        )}
      </BottomSheetView>
    </BottomSheet>
  );
});

NoteSheet.displayName = 'NoteSheet';

export default NoteSheet;

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
  input: {
    ...type.body,
    backgroundColor: colors.bg.secondary,
    borderRadius: radius.md,
    padding: spacing.md,
    color: colors.text.primary,
    borderWidth: 1,
    borderColor: colors.ui.border,
    minHeight: 120,
    textAlignVertical: 'top',
  },
  submitBtn: {
    backgroundColor: '#607D8B',
    borderRadius: radius.md,
    padding: spacing.md,
    alignItems: 'center',
    marginTop: spacing.lg,
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
