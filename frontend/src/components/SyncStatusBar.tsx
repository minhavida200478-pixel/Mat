import React from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { colors, radius, spacing, type } from "@/src/theme";
import { useSync } from "@/src/sync/SyncProvider";

/**
 * Thin status bar shown only when offline or when there are pending writes.
 * Communicates that data is safe and will sync automatically.
 */
export default function SyncStatusBar() {
  const { online, pending, syncing } = useSync();

  if (online && pending === 0) return null;

  let bg = "#FBE9E7";
  let fg = "#C1502E";
  let icon: any = "cloud-offline-outline";
  let text = "Offline — changes are saved on this device";

  if (online && pending > 0) {
    bg = "#FFF6E5";
    fg = "#9A6B00";
    icon = "cloud-upload-outline";
    text = syncing
      ? `Syncing ${pending} change${pending === 1 ? "" : "s"}…`
      : `${pending} change${pending === 1 ? "" : "s"} pending sync`;
  } else if (!online && pending > 0) {
    text = `Offline — ${pending} change${pending === 1 ? "" : "s"} will sync when reconnected`;
  }

  return (
    <View style={[styles.bar, { backgroundColor: bg }]} testID="sync-status-bar">
      {syncing ? (
        <ActivityIndicator size="small" color={fg} />
      ) : (
        <Ionicons name={icon} size={16} color={fg} />
      )}
      <Text style={[styles.text, { color: fg }]} testID="sync-status-text">
        {text}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.xs,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radius.md,
    marginHorizontal: spacing.screen,
    marginBottom: spacing.sm,
  },
  text: { ...type.bodySm, fontWeight: "600", flex: 1 },
});
