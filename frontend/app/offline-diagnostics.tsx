import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import React, { useEffect, useState } from "react";
import {
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { colors, radius, spacing, type } from "@/src/theme";
import {
  clearQueue,
  flush,
  getForcedOffline,
  getQueue,
  isFlushing,
  isOnline,
  pendingCount,
  setForcedOffline,
  subscribe,
  syncWrite,
  type QueuedOp,
} from "@/src/sync/offlineQueue";

export default function OfflineDiagnosticsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [, setTick] = useState(0);

  useEffect(() => {
    const unsub = subscribe(() => setTick((t) => t + 1));
    return () => unsub();
  }, []);

  const online = isOnline();
  const forced = getForcedOffline();
  const pending = pendingCount();
  const flushing = isFlushing();
  const queue: QueuedOp[] = getQueue();

  const queueTestWrite = async () => {
    await syncWrite("POST", "/water", { amount_ml: 250 }, "Diagnostics: Water +250ml");
    setTick((t) => t + 1);
  };

  return (
    <View style={styles.screen}>
      <View style={[styles.topbar, { paddingTop: insets.top + spacing.sm }]}>
        <TouchableOpacity testID="diag-back" onPress={() => router.back()} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.text.primary} />
        </TouchableOpacity>
        <Text style={styles.topTitle}>Offline diagnostics</Text>
        <View style={styles.iconBtn} />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.screen, paddingBottom: insets.bottom + 40 }}>
        <View style={styles.statusCard}>
          <View style={styles.statusRow}>
            <Text style={styles.statusLabel}>Connection</Text>
            <View style={[styles.pill, { backgroundColor: online ? colors.status.success + "20" : "#FBE9E7" }]}>
              <Ionicons
                name={online ? "cloud-done-outline" : "cloud-offline-outline"}
                size={14}
                color={online ? colors.status.success : "#C1502E"}
              />
              <Text style={[styles.pillText, { color: online ? colors.status.success : "#C1502E" }]} testID="diag-online">
                {online ? "Online" : "Offline"}
              </Text>
            </View>
          </View>
          <View style={styles.statusRow}>
            <Text style={styles.statusLabel}>Pending writes</Text>
            <Text style={styles.statusValue} testID="diag-pending">{pending}</Text>
          </View>
          <View style={styles.statusRow}>
            <Text style={styles.statusLabel}>Syncing</Text>
            <Text style={styles.statusValue}>{flushing ? "Yes" : "No"}</Text>
          </View>
        </View>

        <View style={styles.toggleRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.toggleTitle}>Simulate offline</Text>
            <Text style={styles.toggleSub}>Force the queue to hold writes, then turn off to watch them sync.</Text>
          </View>
          <Switch
            testID="diag-offline-toggle"
            value={forced}
            onValueChange={(v) => setForcedOffline(v)}
            trackColor={{ true: "#C1502E", false: colors.bg.tertiary }}
            thumbColor="#fff"
          />
        </View>

        <TouchableOpacity testID="diag-queue-write" style={styles.actionBtn} onPress={queueTestWrite} activeOpacity={0.85}>
          <Ionicons name="add-circle-outline" size={18} color="#fff" />
          <Text style={styles.actionText}>Queue test write (Water +250ml)</Text>
        </TouchableOpacity>

        <View style={styles.secondaryRow}>
          <TouchableOpacity testID="diag-flush" style={styles.secondaryBtn} onPress={() => flush()}>
            <Ionicons name="sync-outline" size={16} color={colors.brand.primary} />
            <Text style={styles.secondaryText}>Flush now</Text>
          </TouchableOpacity>
          <TouchableOpacity testID="diag-clear" style={styles.secondaryBtn} onPress={() => clearQueue()}>
            <Ionicons name="trash-outline" size={16} color={colors.status.periodActive} />
            <Text style={[styles.secondaryText, { color: colors.status.periodActive }]}>Clear queue</Text>
          </TouchableOpacity>
        </View>

        <Text style={styles.sectionLabel}>Queued operations</Text>
        {queue.length === 0 ? (
          <View style={styles.card}>
            <Text style={styles.emptyText}>Queue is empty. Writes go straight to the server when online.</Text>
          </View>
        ) : (
          queue.map((op) => (
            <View key={op.id} style={styles.opRow} testID="diag-op-row">
              <Ionicons name="document-outline" size={16} color={colors.text.secondary} />
              <View style={{ flex: 1, marginLeft: spacing.sm }}>
                <Text style={styles.opLabel}>{op.label}</Text>
                <Text style={styles.opMeta}>{op.method} {op.path} · {op.tries} tr{op.tries === 1 ? "y" : "ies"}</Text>
              </View>
            </View>
          ))
        )}

        <View style={styles.note}>
          <Ionicons name="information-circle-outline" size={15} color={colors.text.tertiary} />
          <Text style={styles.noteText}>
            Writes are de-duplicated with an idempotency key, so replaying the queue never creates
            duplicates. On a real device, true airplane-mode is detected automatically.
          </Text>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg.secondary },
  topbar: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: spacing.md, paddingBottom: spacing.sm,
    backgroundColor: colors.bg.primary, borderBottomWidth: 1, borderBottomColor: colors.ui.divider,
  },
  topTitle: { ...type.h3, color: colors.text.primary },
  iconBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  statusCard: {
    backgroundColor: colors.bg.primary, borderRadius: radius.lg, borderWidth: 1,
    borderColor: colors.ui.border, padding: spacing.lg,
  },
  statusRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: spacing.xs },
  statusLabel: { ...type.body, color: colors.text.secondary },
  statusValue: { ...type.body, color: colors.text.primary, fontWeight: "700" },
  pill: { flexDirection: "row", alignItems: "center", gap: 4, paddingVertical: 4, paddingHorizontal: spacing.sm, borderRadius: radius.pill },
  pillText: { ...type.bodySm, fontWeight: "700" },
  toggleRow: {
    flexDirection: "row", alignItems: "center", backgroundColor: colors.bg.primary,
    borderRadius: radius.md, borderWidth: 1, borderColor: colors.ui.border,
    padding: spacing.md, marginTop: spacing.md,
  },
  toggleTitle: { ...type.body, color: colors.text.primary, fontWeight: "600" },
  toggleSub: { ...type.bodySm, color: colors.text.tertiary, marginTop: 2 },
  actionBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.xs,
    backgroundColor: colors.brand.primary, paddingVertical: spacing.md, borderRadius: radius.pill,
    marginTop: spacing.md,
  },
  actionText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  secondaryRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm },
  secondaryBtn: {
    flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    backgroundColor: colors.bg.primary, borderWidth: 1, borderColor: colors.ui.border,
    paddingVertical: spacing.md, borderRadius: radius.md,
  },
  secondaryText: { ...type.bodySm, color: colors.brand.primary, fontWeight: "600" },
  sectionLabel: { ...type.caption, color: colors.text.tertiary, marginTop: spacing.xl, marginBottom: spacing.sm },
  card: { backgroundColor: colors.bg.primary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.ui.border, padding: spacing.md },
  emptyText: { ...type.bodySm, color: colors.text.secondary },
  opRow: {
    flexDirection: "row", alignItems: "center", backgroundColor: colors.bg.primary,
    borderRadius: radius.md, borderWidth: 1, borderColor: colors.ui.border,
    padding: spacing.md, marginBottom: spacing.sm,
  },
  opLabel: { ...type.body, color: colors.text.primary },
  opMeta: { ...type.caption, color: colors.text.tertiary, textTransform: "none", marginTop: 2 },
  note: { flexDirection: "row", gap: 6, marginTop: spacing.lg, alignItems: "flex-start" },
  noteText: { ...type.bodySm, color: colors.text.tertiary, flex: 1 },
});
