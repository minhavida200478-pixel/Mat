// Per-day health-event view shown inside the Calendar day-detail card.
// Merged from the former Timeline screen: filter chips + search + tap-to-open detail.
import { Ionicons } from "@expo/vector-icons";
import { useMemo, useRef, useState } from "react";
import { Platform, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import * as Haptics from "expo-haptics";

import { EventDetailSheet, EventDetailSheetRef } from "@/src/components/BottomSheet";
import { colors, radius, spacing, type } from "@/src/theme";

import { EVENT_TYPES, EventItem, getEventInfo, HealthEvent } from "./eventUtils";

export function DayEvents({
  events,
  onDeleted,
}: {
  events: HealthEvent[];
  onDeleted: (id: string) => void;
}) {
  const [selectedType, setSelectedType] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [showSearch, setShowSearch] = useState(false);
  const eventDetailRef = useRef<EventDetailSheetRef>(null);

  const filtered = useMemo(() => {
    let list = events;
    if (selectedType !== "all") {
      list = list.filter((e) => e.event_type === selectedType);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter((e) => {
        const info = getEventInfo(e);
        return (
          info.title.toLowerCase().includes(q) ||
          info.subtitle.toLowerCase().includes(q) ||
          e.note?.toLowerCase().includes(q) ||
          e.event_type.toLowerCase().includes(q)
        );
      });
    }
    return [...list].sort(
      (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
    );
  }, [events, selectedType, searchQuery]);

  const handleEventPress = (event: HealthEvent) => {
    if (Platform.OS !== "web") Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    eventDetailRef.current?.open(event);
  };

  const handleTypeSelect = (key: string) => {
    if (Platform.OS !== "web") Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setSelectedType(key);
  };

  return (
    <View testID="calendar-day-events">
      {/* Toolbar: filter chips + search toggle */}
      <View style={styles.toolbar}>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.chipsRow}
          style={{ flex: 1 }}
        >
          {EVENT_TYPES.map(({ key, label, icon, color }) => {
            const isSel = selectedType === key;
            return (
              <TouchableOpacity
                key={key}
                testID={`calendar-filter-${key}`}
                style={[styles.chip, isSel && { backgroundColor: color, borderColor: color }]}
                onPress={() => handleTypeSelect(key)}
                activeOpacity={0.7}
              >
                <Ionicons name={icon as any} size={14} color={isSel ? "#fff" : color} />
                <Text style={[styles.chipLabel, isSel && { color: "#fff" }]}>{label}</Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>
        <TouchableOpacity
          testID="calendar-search-toggle"
          style={styles.searchToggle}
          onPress={() => {
            setShowSearch((s) => !s);
            if (showSearch) setSearchQuery("");
          }}
          activeOpacity={0.7}
        >
          <Ionicons name={showSearch ? "close" : "search"} size={18} color={colors.text.primary} />
        </TouchableOpacity>
      </View>

      {/* Search bar */}
      {showSearch ? (
        <View style={styles.searchBar}>
          <Ionicons name="search-outline" size={16} color={colors.text.tertiary} />
          <TextInput
            testID="calendar-search-input"
            style={styles.searchInput}
            placeholder="Search this day…"
            placeholderTextColor={colors.text.tertiary}
            value={searchQuery}
            onChangeText={setSearchQuery}
            autoFocus
          />
          {searchQuery.length > 0 ? (
            <TouchableOpacity onPress={() => setSearchQuery("")}>
              <Ionicons name="close-circle" size={16} color={colors.text.tertiary} />
            </TouchableOpacity>
          ) : null}
        </View>
      ) : null}

      {/* Event list */}
      {filtered.length > 0 ? (
        <View style={{ marginTop: spacing.sm }}>
          {filtered.map((e) => (
            <EventItem key={e.id} event={e} onPress={handleEventPress} />
          ))}
        </View>
      ) : (
        <Text style={styles.empty} testID="calendar-day-empty">
          {events.length === 0
            ? "No entries for this day. Tap Log to add one."
            : "No events match this filter."}
        </Text>
      )}

      <EventDetailSheet ref={eventDetailRef} onDelete={onDeleted} onEdit={() => {}} />
    </View>
  );
}

const styles = StyleSheet.create({
  toolbar: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  chipsRow: { gap: spacing.xs, paddingRight: spacing.sm },
  chip: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.sm,
    paddingVertical: 5,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.ui.border,
    backgroundColor: colors.bg.primary,
    gap: 4,
    marginRight: spacing.xs,
  },
  chipLabel: { ...type.caption, color: colors.text.secondary, fontWeight: "600", textTransform: "none" },
  searchToggle: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: colors.bg.tertiary,
    alignItems: "center",
    justifyContent: "center",
  },
  searchBar: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.bg.secondary,
    marginTop: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.ui.border,
    gap: spacing.sm,
  },
  searchInput: { flex: 1, ...type.bodySm, color: colors.text.primary, paddingVertical: spacing.sm },
  empty: { ...type.body, color: colors.text.tertiary, marginTop: spacing.md },
});
