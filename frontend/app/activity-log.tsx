import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api/client";
import { colors, radius, spacing, type } from "@/src/theme";

type AuditItem = {
  ts: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  summary: string;
};

const ENTITY_ICON: Record<string, string> = {
  cycle: "water-outline",
  medication: "medical-outline",
  daily_log: "create-outline",
  health_event: "pulse-outline",
  backup: "archive-outline",
};

const ACTION_COLOR: Record<string, string> = {
  created: "#1F9D55",
  updated: "#2E7DD1",
  deleted: "#D64545",
  restored: "#8A63D2",
  backed_up: "#8A63D2",
};

function relTime(iso: string): string {
  const then = new Date(iso).getTime();
  const diff = Date.now() - then;
  const m = Math.round(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  if (d < 7) return `${d}d ago`;
  return new Date(iso).toLocaleDateString([], { month: "short", day: "numeric" });
}

export default function ActivityLogScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [items, setItems] = useState<AuditItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [cursor, setCursor] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const fetchPage = useCallback(async (before: string | null) => {
    const qs = `limit=30${before ? `&before=${encodeURIComponent(before)}` : ""}`;
    const res = await api.get<{ items: AuditItem[]; next_before: string | null }>(
      `/audit-logs?${qs}`,
    );
    return res;
  }, []);

  const load = useCallback(async () => {
    try {
      const res = await fetchPage(null);
      setItems(res.items);
      setCursor(res.next_before);
      setDone(!res.next_before);
    } catch (e) {
      console.error("Failed to load audit logs:", e);
    } finally {
      setLoading(false);
    }
  }, [fetchPage]);

  useEffect(() => {
    load();
  }, [load]);

  const loadMore = useCallback(async () => {
    if (loadingMore || done || !cursor) return;
    setLoadingMore(true);
    try {
      const res = await fetchPage(cursor);
      setItems((prev) => [...prev, ...res.items]);
      setCursor(res.next_before);
      setDone(!res.next_before);
    } catch {
      /* ignore */
    } finally {
      setLoadingMore(false);
    }
  }, [cursor, done, loadingMore, fetchPage]);

  return (
    <View style={styles.screen}>
      <View style={[styles.topbar, { paddingTop: insets.top + spacing.sm }]}>
        <TouchableOpacity testID="activity-back" onPress={() => router.back()} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.text.primary} />
        </TouchableOpacity>
        <Text style={styles.topTitle}>Activity log</Text>
        <View style={styles.iconBtn} />
      </View>

      {loading ? (
        <View style={styles.center} testID="activity-loading">
          <ActivityIndicator size="large" color={colors.brand.primary} />
        </View>
      ) : items.length === 0 ? (
        <View style={styles.center} testID="activity-empty">
          <Ionicons name="time-outline" size={40} color={colors.text.tertiary} />
          <Text style={styles.emptyText}>No activity yet. Your changes will appear here.</Text>
        </View>
      ) : (
        <FlatList
          testID="activity-list"
          data={items}
          keyExtractor={(_, i) => String(i)}
          contentContainerStyle={{ padding: spacing.screen, paddingBottom: insets.bottom + 40 }}
          onEndReachedThreshold={0.4}
          onEndReached={loadMore}
          ListHeaderComponent={
            <Text style={styles.subhead}>A private history of changes to your data.</Text>
          }
          renderItem={({ item }) => (
            <View style={styles.row} testID="activity-row">
              <View style={[styles.iconWrap, { backgroundColor: (ACTION_COLOR[item.action] || colors.brand.primary) + "18" }]}>
                <Ionicons
                  name={(ENTITY_ICON[item.entity_type] || "ellipse-outline") as any}
                  size={18}
                  color={ACTION_COLOR[item.action] || colors.brand.primary}
                />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.summary}>{item.summary}</Text>
                <View style={styles.metaRow}>
                  <Text style={[styles.action, { color: ACTION_COLOR[item.action] || colors.text.secondary }]}>
                    {item.action}
                  </Text>
                  <Text style={styles.dot}>·</Text>
                  <Text style={styles.time}>{relTime(item.ts)}</Text>
                </View>
              </View>
            </View>
          )}
          ListFooterComponent={
            loadingMore ? <ActivityIndicator color={colors.brand.primary} style={{ marginVertical: 16 }} /> : null
          }
        />
      )}
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
  center: { flex: 1, alignItems: "center", justifyContent: "center", gap: spacing.sm, padding: spacing.xl },
  emptyText: { ...type.body, color: colors.text.secondary, textAlign: "center" },
  subhead: { ...type.bodySm, color: colors.text.tertiary, marginBottom: spacing.md },
  row: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.bg.primary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.ui.border,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  iconWrap: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center", marginRight: spacing.md },
  summary: { ...type.body, color: colors.text.primary },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 2 },
  action: { ...type.caption, fontWeight: "700", textTransform: "capitalize" },
  dot: { color: colors.text.tertiary },
  time: { ...type.caption, color: colors.text.tertiary, textTransform: "none" },
});
