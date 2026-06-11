import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { api } from "@/src/api/client";
import { colors, radius, spacing, type } from "@/src/theme";
import { todayISO } from "@/src/utils/cycle";

type Summary = {
  headline: string;
  cycle_day: number | null;
  phase: string | null;
  days_until_next_period: number | null;
  next_period_date: string | null;
  water: { total_ml: number; goal_ml: number; percentage: number };
  meals_completed: number;
  meals_goal: number;
  medications_taken: number;
  medications_planned: number;
  symptoms_logged: number;
  mood_entries: number;
  has_cycle_data: boolean;
};

function periodText(du: number | null): string | null {
  if (du === null) return null;
  if (du > 1) return `Period expected in ${du} days`;
  if (du === 1) return "Period expected tomorrow";
  if (du === 0) return "Period expected today";
  return `Period ${Math.abs(du)} day${Math.abs(du) === 1 ? "" : "s"} late`;
}

export default function DailySummaryCard({ refreshTrigger }: { refreshTrigger?: number }) {
  const [data, setData] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const d = await api.get<Summary>(`/daily-summary?today=${todayISO()}`);
      setData(d);
    } catch {
      /* handled globally */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load, refreshTrigger]);

  if (loading) {
    return (
      <View style={[styles.card, styles.loader]} testID="daily-summary-loading">
        <ActivityIndicator color={colors.brand.primary} />
      </View>
    );
  }
  if (!data) return null;

  const pt = periodText(data.days_until_next_period);
  const metrics = [
    {
      key: "water",
      icon: "water-outline",
      color: "#2E9BD6",
      label: "Water",
      value: `${data.water.percentage}%`,
    },
    {
      key: "meals",
      icon: "restaurant-outline",
      color: "#E0712F",
      label: "Meals",
      value: `${data.meals_completed}/${data.meals_goal}`,
    },
    {
      key: "meds",
      icon: "medical-outline",
      color: "#9B59B6",
      label: "Meds",
      value: data.medications_planned > 0
        ? `${data.medications_taken}/${data.medications_planned}`
        : "—",
    },
    {
      key: "symptoms",
      icon: "pulse-outline",
      color: colors.brand.primary,
      label: "Symptoms",
      value: `${data.symptoms_logged}`,
    },
    {
      key: "mood",
      icon: "happy-outline",
      color: colors.status.fertile,
      label: "Mood",
      value: `${data.mood_entries}`,
    },
  ];

  return (
    <View style={styles.card} testID="daily-summary-card">
      <View style={styles.headerRow}>
        <Ionicons name="sparkles-outline" size={16} color={colors.brand.primary} />
        <Text style={styles.headline} testID="daily-summary-headline">
          {data.headline}
        </Text>
      </View>
      {pt && (
        <Text style={styles.periodLine} testID="daily-summary-period">
          {pt}
          {data.next_period_date && data.days_until_next_period !== null && data.days_until_next_period > 0
            ? ` · ${data.next_period_date}`
            : ""}
        </Text>
      )}
      <View style={styles.metricsRow}>
        {metrics.map((m) => (
          <View key={m.key} style={styles.metric} testID={`daily-summary-${m.key}`}>
            <View style={[styles.metricIcon, { backgroundColor: m.color + "18" }]}>
              <Ionicons name={m.icon as any} size={16} color={m.color} />
            </View>
            <Text style={styles.metricValue}>{m.value}</Text>
            <Text style={styles.metricLabel}>{m.label}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.bg.primary,
    marginHorizontal: spacing.screen,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.ui.border,
    padding: spacing.lg,
  },
  loader: { alignItems: "center", justifyContent: "center", minHeight: 120 },
  headerRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  headline: { ...type.h3, color: colors.text.primary, flex: 1 },
  periodLine: { ...type.bodySm, color: colors.status.periodActive, fontWeight: "600", marginTop: spacing.xs },
  metricsRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: spacing.lg,
  },
  metric: { alignItems: "center", flex: 1 },
  metricIcon: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 6,
  },
  metricValue: { ...type.body, color: colors.text.primary, fontWeight: "700" },
  metricLabel: { ...type.caption, color: colors.text.tertiary, textTransform: "none", marginTop: 1 },
});
