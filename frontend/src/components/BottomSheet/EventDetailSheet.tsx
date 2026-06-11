// Event detail bottom sheet with view/edit/delete functionality
import React, { useState, forwardRef, useCallback, useImperativeHandle, useRef } from 'react';
import {
  StyleSheet,
  View,
  Text,
  TouchableOpacity,
  ActivityIndicator,
  Platform,
  Alert,
} from 'react-native';
import BottomSheet, { BottomSheetScrollView } from '@gorhom/bottom-sheet';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';

import { colors, radius, spacing, type } from '@/src/theme';
import { api } from '@/src/api/client';

// Event type configuration
const EVENT_CONFIGS: Record<string, { icon: string; color: string; label: string }> = {
  water: { icon: 'water-outline', color: '#3498DB', label: 'Hydration' },
  meal: { icon: 'restaurant-outline', color: '#E67E22', label: 'Meal' },
  medication: { icon: 'medical-outline', color: '#9B59B6', label: 'Medication' },
  mood: { icon: 'happy-outline', color: '#F1C40F', label: 'Mood' },
  symptom: { icon: 'pulse-outline', color: '#E74C3C', label: 'Symptom' },
  sexual_activity: { icon: 'heart-outline', color: '#E91E63', label: 'Intimacy' },
  note: { icon: 'document-text-outline', color: '#34495E', label: 'Note' },
  period: { icon: 'water', color: '#E74C3C', label: 'Period' },
};

type HealthEvent = {
  id: string;
  event_type: string;
  timestamp: string;
  date: string;
  data: Record<string, any>;
  note?: string;
  visibility: string;
  tags: string[];
  created_at: string;
};

export type EventDetailSheetRef = {
  open: (event: HealthEvent) => void;
  close: () => void;
};

type Props = {
  onDelete?: (eventId: string) => void;
  onEdit?: (event: HealthEvent) => void;
};

const EventDetailSheet = forwardRef<EventDetailSheetRef, Props>(({ onDelete, onEdit }, ref) => {
  const bottomSheetRef = useRef<BottomSheet>(null);
  const [event, setEvent] = useState<HealthEvent | null>(null);
  const [deleting, setDeleting] = useState(false);

  useImperativeHandle(ref, () => ({
    open: (eventData: HealthEvent) => {
      setEvent(eventData);
      setDeleting(false);
      bottomSheetRef.current?.expand();
    },
    close: () => bottomSheetRef.current?.close(),
  }));

  const triggerHaptic = useCallback((style: 'light' | 'medium' | 'success' | 'error') => {
    if (Platform.OS !== 'web') {
      if (style === 'success') {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      } else if (style === 'error') {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      } else {
        Haptics.impactAsync(
          style === 'light' 
            ? Haptics.ImpactFeedbackStyle.Light 
            : Haptics.ImpactFeedbackStyle.Medium
        );
      }
    }
  }, []);

  const handleDelete = useCallback(async () => {
    if (!event) return;

    Alert.alert(
      'Delete Event',
      'Are you sure you want to delete this event? This action cannot be undone.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            setDeleting(true);
            try {
              await api.del(`/health-events/${event.id}`);
              triggerHaptic('success');
              onDelete?.(event.id);
              bottomSheetRef.current?.close();
            } catch (error) {
              console.error('Failed to delete event:', error);
              triggerHaptic('error');
              Alert.alert('Error', 'Failed to delete event. Please try again.');
            } finally {
              setDeleting(false);
            }
          },
        },
      ]
    );
  }, [event, onDelete, triggerHaptic]);

  const handleEdit = useCallback(() => {
    if (!event) return;
    triggerHaptic('light');
    onEdit?.(event);
    bottomSheetRef.current?.close();
  }, [event, onEdit, triggerHaptic]);

  const formatDateTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return {
      date: date.toLocaleDateString('en-US', { 
        weekday: 'long', 
        year: 'numeric', 
        month: 'long', 
        day: 'numeric' 
      }),
      time: date.toLocaleTimeString('en-US', { 
        hour: '2-digit', 
        minute: '2-digit' 
      }),
    };
  };

  const renderEventDetails = () => {
    if (!event) return null;

    const config = EVENT_CONFIGS[event.event_type] || EVENT_CONFIGS.note;
    const { date, time } = formatDateTime(event.timestamp);

    return (
      <View style={styles.detailsContainer}>
        {/* Event Type Header */}
        <View style={[styles.typeHeader, { backgroundColor: config.color + '15' }]}>
          <View style={[styles.typeIcon, { backgroundColor: config.color }]}>
            <Ionicons name={config.icon as any} size={28} color="#fff" />
          </View>
          <View style={styles.typeInfo}>
            <Text style={styles.typeLabel}>{config.label}</Text>
            <Text style={styles.typeTime}>{time}</Text>
          </View>
        </View>

        {/* Date */}
        <View style={styles.detailRow}>
          <Ionicons name="calendar-outline" size={20} color={colors.text.tertiary} />
          <Text style={styles.detailText}>{date}</Text>
        </View>

        {/* Event-specific details */}
        {renderSpecificDetails()}

        {/* Note */}
        {event.note && (
          <View style={styles.noteSection}>
            <Text style={styles.sectionTitle}>Note</Text>
            <Text style={styles.noteText}>{event.note}</Text>
          </View>
        )}

        {/* Tags */}
        {event.tags && event.tags.length > 0 && (
          <View style={styles.tagsSection}>
            <Text style={styles.sectionTitle}>Tags</Text>
            <View style={styles.tagsRow}>
              {event.tags.map((tag, index) => (
                <View key={index} style={styles.tag}>
                  <Text style={styles.tagText}>{tag}</Text>
                </View>
              ))}
            </View>
          </View>
        )}

        {/* Visibility */}
        <View style={styles.visibilityRow}>
          <Ionicons 
            name={event.visibility === 'private' ? 'lock-closed-outline' : 'people-outline'} 
            size={16} 
            color={colors.text.tertiary} 
          />
          <Text style={styles.visibilityText}>
            {event.visibility === 'private' ? 'Private' : 'Shared with partner'}
          </Text>
        </View>
      </View>
    );
  };

  const renderSpecificDetails = () => {
    if (!event) return null;

    const data = event.data || {};

    switch (event.event_type) {
      case 'water':
        return (
          <View style={styles.specificDetails}>
            <DetailItem label="Amount" value={`${data.amount_ml || 250}ml`} />
            {data.beverage_type && <DetailItem label="Beverage" value={data.beverage_type} />}
          </View>
        );

      case 'meal':
        return (
          <View style={styles.specificDetails}>
            {data.meal_type && <DetailItem label="Meal Type" value={capitalize(data.meal_type)} />}
            {data.status && <DetailItem label="Status" value={capitalize(data.status)} />}
            {data.calories && <DetailItem label="Calories" value={`${data.calories} kcal`} />}
          </View>
        );

      case 'medication':
        return (
          <View style={styles.specificDetails}>
            {data.name && <DetailItem label="Medication" value={data.name} />}
            {data.dosage && <DetailItem label="Dosage" value={data.dosage} />}
            {data.category && <DetailItem label="Category" value={capitalize(data.category)} />}
          </View>
        );

      case 'mood':
        const moodEmojis: Record<string, string> = {
          great: '😊 Great',
          good: '🙂 Good',
          okay: '😐 Okay',
          low: '😔 Low',
          bad: '😢 Bad',
        };
        return (
          <View style={styles.specificDetails}>
            {data.level && <DetailItem label="Mood" value={moodEmojis[data.level] || data.level} />}
            {data.energy && <DetailItem label="Energy" value={`${data.energy}/5`} />}
          </View>
        );

      case 'symptom':
        return (
          <View style={styles.specificDetails}>
            {data.type && <DetailItem label="Symptom" value={capitalize(data.type)} />}
            {data.severity && <DetailItem label="Severity" value={`${data.severity}/5`} />}
            {data.location && <DetailItem label="Location" value={data.location} />}
          </View>
        );

      case 'sexual_activity':
        return (
          <View style={styles.specificDetails}>
            <DetailItem 
              label="Protection" 
              value={data.protection_used ? 'Yes' : 'No'} 
            />
            {data.partner_involved !== undefined && (
              <DetailItem label="Partner" value={data.partner_involved ? 'Yes' : 'Solo'} />
            )}
          </View>
        );

      case 'period':
        return (
          <View style={styles.specificDetails}>
            {data.flow && <DetailItem label="Flow" value={capitalize(data.flow)} />}
          </View>
        );

      default:
        return null;
    }
  };

  return (
    <BottomSheet
      ref={bottomSheetRef}
      index={-1}
      snapPoints={['70%']}
      enablePanDownToClose
      onChange={(idx) => {
        // When the sheet fully closes, drop the event so no content (incl. the
        // "Event Details" title) renders — avoids a web layout leak when closed.
        if (idx === -1) setEvent(null);
      }}
      backgroundStyle={styles.sheetBackground}
      handleIndicatorStyle={styles.handleIndicator}
    >
      <BottomSheetScrollView contentContainerStyle={styles.content}>
        {event ? (
          <>
            <Text style={styles.title}>Event Details</Text>

            {renderEventDetails()}

            {/* Action Buttons */}
            <View style={styles.actionsRow}>
              <TouchableOpacity
                style={styles.editBtn}
                onPress={handleEdit}
                activeOpacity={0.7}
              >
                <Ionicons name="pencil-outline" size={20} color={colors.brand.primary} />
                <Text style={styles.editBtnText}>Edit</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={styles.deleteBtn}
                onPress={handleDelete}
                activeOpacity={0.7}
                disabled={deleting}
              >
                {deleting ? (
                  <ActivityIndicator size="small" color="#fff" />
                ) : (
                  <>
                    <Ionicons name="trash-outline" size={20} color="#fff" />
                    <Text style={styles.deleteBtnText}>Delete</Text>
                  </>
                )}
              </TouchableOpacity>
            </View>
          </>
        ) : null}
      </BottomSheetScrollView>
    </BottomSheet>
  );
});

// Helper component for detail items
const DetailItem = ({ label, value }: { label: string; value: string }) => (
  <View style={styles.detailItem}>
    <Text style={styles.detailLabel}>{label}</Text>
    <Text style={styles.detailValue}>{value}</Text>
  </View>
);

const capitalize = (str: string) => str.charAt(0).toUpperCase() + str.slice(1);

EventDetailSheet.displayName = 'EventDetailSheet';

export default EventDetailSheet;

const styles = StyleSheet.create({
  sheetBackground: {
    backgroundColor: colors.bg.primary,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
  },
  handleIndicator: {
    backgroundColor: colors.ui.divider,
    width: 40,
  },
  content: {
    padding: spacing.lg,
    paddingBottom: spacing.xxl,
  },
  title: {
    ...type.h2,
    color: colors.text.primary,
    marginBottom: spacing.lg,
    textAlign: 'center',
  },
  detailsContainer: {
    gap: spacing.md,
  },
  typeHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: spacing.md,
    borderRadius: radius.lg,
    marginBottom: spacing.sm,
  },
  typeIcon: {
    width: 56,
    height: 56,
    borderRadius: 28,
    alignItems: 'center',
    justifyContent: 'center',
  },
  typeInfo: {
    marginLeft: spacing.md,
    flex: 1,
  },
  typeLabel: {
    ...type.h3,
    color: colors.text.primary,
    fontSize: 20,
  },
  typeTime: {
    ...type.body,
    color: colors.text.secondary,
    marginTop: 2,
  },
  detailRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.xs,
  },
  detailText: {
    ...type.body,
    color: colors.text.secondary,
  },
  specificDetails: {
    backgroundColor: colors.bg.secondary,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.sm,
  },
  detailItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  detailLabel: {
    ...type.bodySm,
    color: colors.text.tertiary,
  },
  detailValue: {
    ...type.body,
    color: colors.text.primary,
    fontWeight: '600',
  },
  noteSection: {
    marginTop: spacing.sm,
  },
  sectionTitle: {
    ...type.caption,
    color: colors.text.tertiary,
    marginBottom: spacing.xs,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  noteText: {
    ...type.body,
    color: colors.text.secondary,
    backgroundColor: colors.bg.secondary,
    padding: spacing.md,
    borderRadius: radius.md,
    lineHeight: 22,
  },
  tagsSection: {
    marginTop: spacing.sm,
  },
  tagsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
  },
  tag: {
    backgroundColor: colors.brand.primary + '15',
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    borderRadius: radius.pill,
  },
  tagText: {
    ...type.caption,
    color: colors.brand.primary,
    fontWeight: '500',
  },
  visibilityRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginTop: spacing.sm,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.ui.divider,
  },
  visibilityText: {
    ...type.caption,
    color: colors.text.tertiary,
  },
  actionsRow: {
    flexDirection: 'row',
    gap: spacing.md,
    marginTop: spacing.xl,
  },
  editBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.brand.primary,
    gap: spacing.xs,
  },
  editBtnText: {
    ...type.body,
    color: colors.brand.primary,
    fontWeight: '600',
  },
  deleteBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.status.error,
    gap: spacing.xs,
  },
  deleteBtnText: {
    ...type.body,
    color: '#fff',
    fontWeight: '600',
  },
});
