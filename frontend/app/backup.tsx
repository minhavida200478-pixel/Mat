import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { useRouter } from "expo-router";
import React, { useCallback, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api/client";
import { useFetch } from "@/src/hooks/useFetch";
import { colors, radius, spacing, type } from "@/src/theme";

type Backup = {
  id: string;
  type?: "manual" | "auto";
  created_at: string;
  counts: Record<string, number>;
  total: number;
};

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString([], {
      month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default function BackupScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const { data, loading, refetch: load } = useFetch<Backup[]>(async () => {
    // Ensure the weekly automatic backup exists (no-ops if a recent one is
    // present). Manual backups are never affected by this.
    try {
      await api.post("/backups/ensure-weekly", {});
    } catch {
      /* non-blocking */
    }
    return api.get<Backup[]>("/backups");
  });
  const backups = data ?? [];

  const createBackup = useCallback(async () => {
    setCreating(true);
    if (Platform.OS !== "web") Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      await api.post("/backup", {});
      await load();
    } catch (e) {
      Alert.alert("Backup failed", "Could not create a backup. Please try again.");
    } finally {
      setCreating(false);
    }
  }, [load]);

  const restore = useCallback((b: Backup) => {
    Alert.alert(
      "Restore this backup?",
      `This replaces all your current data with the snapshot from ${fmtDate(b.created_at)} (${b.total} records). This cannot be undone.`,
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Restore",
          style: "destructive",
          onPress: async () => {
            setBusyId(b.id);
            try {
              const res = await api.post<{ total: number }>(`/backups/${b.id}/restore`, {});
              Alert.alert("Restored", `${res.total} records were restored from this backup.`);
            } catch {
              Alert.alert("Restore failed", "Could not restore this backup. Please try again.");
            } finally {
              setBusyId(null);
            }
          },
        },
      ],
    );
  }, []);

  const remove = useCallback((b: Backup) => {
    Alert.alert("Delete backup?", `Remove the backup from ${fmtDate(b.created_at)}.`, [
      { text: "Cancel", style: "cancel" },
      {
        text: "Delete",
        style: "destructive",
        onPress: async () => {
          try {
            await api.del(`/backups/${b.id}`);
            load();
          } catch {
            /* ignore */
          }
        },
      },
    ]);
  }, [load]);

  return (
    <View style={styles.screen}>
      <View style={[styles.topbar, { paddingTop: insets.top + spacing.sm }]}>
        <TouchableOpacity testID="backup-back" onPress={() => router.back()} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.text.primary} />
        </TouchableOpacity>
        <Text style={styles.topTitle}>Backup & Restore</Text>
        <View style={styles.iconBtn} />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.screen, paddingBottom: insets.bottom + 40 }}>
        <View style={styles.hero}>
          <View style={styles.heroIcon}>
            <Ionicons name="shield-checkmark-outline" size={26} color={colors.brand.primary} />
          </View>
          <Text style={styles.heroTitle}>Protect your history</Text>
          <Text style={styles.heroSub}>
            Create a secure snapshot of your cycles, logs, medications and events. We also keep an
            automatic weekly backup for you — restore any time if something goes wrong.
          </Text>
          <TouchableOpacity
            testID="create-backup-btn"
            style={[styles.primaryBtn, creating && { opacity: 0.6 }]}
            onPress={createBackup}
            disabled={creating}
            activeOpacity={0.85}
          >
            {creating ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <>
                <Ionicons name="cloud-upload-outline" size={18} color="#fff" />
                <Text style={styles.primaryBtnText}>Create backup now</Text>
              </>
            )}
          </TouchableOpacity>
        </View>

        <Text style={styles.sectionLabel}>Your backups</Text>
        {loading ? (
          <ActivityIndicator color={colors.brand.primary} style={{ marginTop: spacing.lg }} />
        ) : backups.length === 0 ? (
          <View style={styles.card} testID="backup-empty">
            <Text style={styles.emptyText}>No backups yet. Create one to safeguard your data.</Text>
          </View>
        ) : (
          backups.map((b) => (
            <View key={b.id} style={styles.card} testID={`backup-${b.id}`}>
              <View style={styles.cardHeader}>
                <Ionicons name="archive-outline" size={20} color={colors.brand.primary} />
                <View style={{ flex: 1, marginLeft: spacing.sm }}>
                  <View style={styles.titleRow}>
                    <Text style={styles.cardTitle}>{fmtDate(b.created_at)}</Text>
                    <View
                      style={[
                        styles.badge,
                        b.type === "auto" ? styles.badgeAuto : styles.badgeManual,
                      ]}
                      testID={`backup-type-${b.id}`}
                    >
                      <Ionicons
                        name={b.type === "auto" ? "sync-outline" : "person-outline"}
                        size={11}
                        color={b.type === "auto" ? colors.brand.primary : colors.text.secondary}
                      />
                      <Text
                        style={[
                          styles.badgeText,
                          { color: b.type === "auto" ? colors.brand.primary : colors.text.secondary },
                        ]}
                      >
                        {b.type === "auto" ? "Auto · weekly" : "Manual"}
                      </Text>
                    </View>
                  </View>
                  <Text style={styles.cardSub}>
                    {b.total} records · {b.counts.cycles || 0} cycles · {b.counts.daily_logs || 0} logs · {b.counts.health_events || 0} events · {b.counts.med_schedules || 0} meds
                  </Text>
                </View>
              </View>
              <View style={styles.actions}>
                <TouchableOpacity
                  testID={`restore-${b.id}`}
                  style={styles.restoreBtn}
                  onPress={() => restore(b)}
                  disabled={busyId === b.id}
                >
                  {busyId === b.id ? (
                    <ActivityIndicator size="small" color={colors.brand.primary} />
                  ) : (
                    <>
                      <Ionicons name="refresh-outline" size={16} color={colors.brand.primary} />
                      <Text style={styles.restoreText}>Restore</Text>
                    </>
                  )}
                </TouchableOpacity>
                <TouchableOpacity testID={`delete-backup-${b.id}`} style={styles.deleteBtn} onPress={() => remove(b)}>
                  <Ionicons name="trash-outline" size={16} color={colors.status.periodActive} />
                  <Text style={[styles.restoreText, { color: colors.status.periodActive }]}>Delete</Text>
                </TouchableOpacity>
              </View>
            </View>
          ))
        )}

        <View style={styles.note}>
          <Ionicons name="information-circle-outline" size={15} color={colors.text.tertiary} />
          <Text style={styles.noteText}>
            An automatic backup is created weekly and only the latest auto backup is kept. Your
            manual backups are never deleted automatically. Restoring replaces your current data
            with the chosen snapshot. Backups are stored privately on your account.
          </Text>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg.secondary },
  topbar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.sm,
    backgroundColor: colors.bg.primary,
    borderBottomWidth: 1,
    borderBottomColor: colors.ui.divider,
  },
  topTitle: { ...type.h3, color: colors.text.primary },
  iconBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  hero: {
    backgroundColor: colors.bg.primary,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.ui.border,
    padding: spacing.lg,
    alignItems: "center",
  },
  heroIcon: {
    width: 56, height: 56, borderRadius: 28,
    backgroundColor: colors.brand.primary + "18",
    alignItems: "center", justifyContent: "center", marginBottom: spacing.sm,
  },
  heroTitle: { ...type.h3, color: colors.text.primary, marginBottom: 4 },
  heroSub: { ...type.bodySm, color: colors.text.secondary, textAlign: "center", marginBottom: spacing.lg },
  primaryBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.xs,
    backgroundColor: colors.brand.primary, paddingVertical: spacing.md, paddingHorizontal: spacing.xl,
    borderRadius: radius.pill, alignSelf: "stretch",
  },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 16 },
  sectionLabel: { ...type.caption, color: colors.text.tertiary, marginTop: spacing.xl, marginBottom: spacing.sm },
  card: {
    backgroundColor: colors.bg.primary, borderRadius: radius.md, borderWidth: 1,
    borderColor: colors.ui.border, padding: spacing.md, marginBottom: spacing.sm,
  },
  cardHeader: { flexDirection: "row", alignItems: "center" },
  titleRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm },
  badge: {
    flexDirection: "row", alignItems: "center", gap: 3,
    paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.pill,
  },
  badgeAuto: { backgroundColor: colors.brand.primary + "18" },
  badgeManual: { backgroundColor: colors.ui.divider },
  badgeText: { fontSize: 10, fontWeight: "700", textTransform: "uppercase", letterSpacing: 0.3 },
  cardTitle: { ...type.body, color: colors.text.primary, fontWeight: "700" },
  cardSub: { ...type.caption, color: colors.text.secondary, textTransform: "none", marginTop: 2 },
  actions: { flexDirection: "row", gap: spacing.lg, marginTop: spacing.md, borderTopWidth: 1, borderTopColor: colors.ui.divider, paddingTop: spacing.sm },
  restoreBtn: { flexDirection: "row", alignItems: "center", gap: 4 },
  deleteBtn: { flexDirection: "row", alignItems: "center", gap: 4 },
  restoreText: { ...type.bodySm, color: colors.brand.primary, fontWeight: "600" },
  emptyText: { ...type.body, color: colors.text.secondary },
  note: { flexDirection: "row", gap: 6, marginTop: spacing.lg, alignItems: "flex-start" },
  noteText: { ...type.bodySm, color: colors.text.tertiary, flex: 1 },
});
