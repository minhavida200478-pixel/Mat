// Shared health-event helpers + a memoized event row, used by the calendar's
// per-day event view (merged from the former Timeline screen).
import { Ionicons } from "@expo/vector-icons";
import React from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";

import { colors, radius, spacing, type } from "@/src/theme";

export type HealthEvent = {
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

export const EVENT_TYPES = [
  { key: "all", label: "All", icon: "layers-outline", color: colors.brand.primary },
  { key: "water", label: "Water", icon: "water-outline", color: "#3498DB" },
  { key: "meal", label: "Meals", icon: "restaurant-outline", color: "#E67E22" },
  { key: "medication", label: "Meds", icon: "medical-outline", color: "#9B59B6" },
  { key: "mood", label: "Mood", icon: "happy-outline", color: "#F1C40F" },
  { key: "symptom", label: "Symptom", icon: "pulse-outline", color: "#E74C3C" },
  { key: "sexual_activity", label: "Activity", icon: "heart-outline", color: "#E91E63" },
  { key: "note", label: "Notes", icon: "document-text-outline", color: "#34495E" },
] as const;

export function formatTime(timestamp: string): string {
  return new Date(timestamp).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
}

export function getEventInfo(event: HealthEvent) {
  const typeConfig = EVENT_TYPES.find((t) => t.key === event.event_type) || EVENT_TYPES[0];
  let title = "";
  let subtitle = "";

  switch (event.event_type) {
    case "water":
      title = `${event.data?.amount_ml || 250}ml Water`;
      subtitle = event.data?.beverage_type || "Water";
      break;
    case "meal":
      title = event.data?.meal_type
        ? `${event.data.meal_type.charAt(0).toUpperCase() + event.data.meal_type.slice(1)}`
        : "Meal";
      subtitle = event.note || (event.data?.status === "skipped" ? "Skipped" : "Logged");
      break;
    case "medication":
      title = event.data?.name || "Medication";
      subtitle = event.data?.dosage || event.data?.category || "";
      break;
    case "mood": {
      const moodEmoji = { great: "😊", good: "🙂", okay: "😐", low: "😔", bad: "😢" };
      title = `Mood: ${event.data?.level || "logged"}`;
      subtitle = moodEmoji[event.data?.level as keyof typeof moodEmoji] || "";
      break;
    }
    case "symptom":
      title = event.data?.type || "Symptom";
      subtitle = event.data?.severity ? `Severity: ${event.data.severity}/5` : "";
      break;
    case "sexual_activity":
      title = "Intimacy";
      subtitle = event.data?.protection_used ? "Protected" : "";
      break;
    case "note":
      title = "Note";
      subtitle = event.note?.substring(0, 50) || "";
      break;
    case "period":
      title = "Period";
      subtitle = event.data?.flow || "Logged";
      break;
    default:
      title = event.event_type.replace(/_/g, " ");
      subtitle = event.note || "";
  }

  return { ...typeConfig, title, subtitle };
}

// Memoized row — only re-renders when its event or handler changes.
export const EventItem = React.memo(function EventItem({
  event,
  onPress,
}: {
  event: HealthEvent;
  onPress: (e: HealthEvent) => void;
}) {
  const info = getEventInfo(event);
  return (
    <TouchableOpacity
      testID={`calendar-event-${event.id}`}
      style={styles.eventItem}
      activeOpacity={0.7}
      onPress={() => onPress(event)}
    >
      <View style={[styles.eventIcon, { backgroundColor: info.color + "15" }]}>
        <Ionicons name={info.icon as any} size={20} color={info.color} />
      </View>
      <View style={styles.eventContent}>
        <Text style={styles.eventTitle}>{info.title}</Text>
        {info.subtitle ? (
          <Text style={styles.eventSubtitle} numberOfLines={1}>{info.subtitle}</Text>
        ) : null}
        {event.note && event.event_type !== "note" ? (
          <Text style={styles.eventNote} numberOfLines={1}>📝 {event.note}</Text>
        ) : null}
      </View>
      <View style={styles.eventRight}>
        <Text style={styles.eventTime}>{formatTime(event.timestamp)}</Text>
        <Ionicons name="chevron-forward" size={16} color={colors.text.tertiary} />
      </View>
    </TouchableOpacity>
  );
});

const styles = StyleSheet.create({
  eventItem: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.bg.primary,
    padding: spacing.md,
    borderRadius: radius.md,
    marginBottom: spacing.xs,
    borderWidth: 1,
    borderColor: colors.ui.border,
  },
  eventIcon: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center" },
  eventContent: { flex: 1, marginLeft: spacing.md },
  eventTitle: { ...type.body, color: colors.text.primary, fontWeight: "600" },
  eventSubtitle: { ...type.bodySm, color: colors.text.secondary, marginTop: 2 },
  eventNote: { ...type.caption, color: colors.text.tertiary, marginTop: 4, fontStyle: "italic" },
  eventRight: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  eventTime: { ...type.caption, color: colors.text.tertiary },
});
