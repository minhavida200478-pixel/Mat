import { Ionicons } from "@expo/vector-icons";
import { Image } from "expo-image";
import { useFocusEffect, useRouter } from "expo-router";
import React, { useCallback, useState, useRef } from "react";
import {
  ActivityIndicator,
  Alert,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import CycleRing from "@/src/components/CycleRing";
import DailySummaryCard from "@/src/components/DailySummaryCard";
import SyncStatusBar from "@/src/components/SyncStatusBar";
import HydrationWidget from "@/src/components/HydrationWidget";
import MealWidget from "@/src/components/MealWidget";
import SexualActivityWidget from "@/src/components/SexualActivityWidget";
import MedicationWidget from "@/src/components/MedicationWidget";
import QuickCaptureOverlay from "@/src/components/QuickCaptureOverlay";
import { Card } from "@/src/components/ui";
import { PREDICTION_DISCLAIMER } from "@/src/constants";
import { api } from "@/src/api/client";
import { syncWidgetData } from "@/src/widgets/widgetData";
import { useAuth } from "@/src/ctx/AuthContext";
import { useFetch } from "@/src/hooks/useFetch";
import { colors, media, radius, spacing, type } from "@/src/theme";
import {
  currentPhaseLabel,
  formatLong,
  formatNice,
  Prediction,
  todayISO,
} from "@/src/utils/cycle";

type DashData = {
  prediction: Prediction;
  today_log: any | null;
  user: { full_name?: string | null };
};

const QUICK_ACTIONS = [
  { key: "period", label: "Start Period", icon: "water", color: colors.status.periodActive },
  { key: "symptom", label: "Log Symptoms", icon: "pulse", color: colors.brand.primary },
  { key: "mood", label: "Log Mood", icon: "happy", color: colors.status.fertile },
];

export default function Dashboard() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const [refreshing, setRefreshing] = useState(false);
  const [hydrationRefresh, setHydrationRefresh] = useState(0);
  const [mealRefresh, setMealRefresh] = useState(0);
  const [activityRefresh, setActivityRefresh] = useState(0);
  const [medicationRefresh, setMedicationRefresh] = useState(0);
  const [summaryRefresh, setSummaryRefresh] = useState(0);

  const { data, loading, refetch } = useFetch<DashData>(
    async () => {
      const d = await api.get<DashData>(`/dashboard?today=${todayISO()}`);
      // Refresh the Android home-screen widget cache (no-op on web/iOS/Expo Go).
      syncWidgetData();
      return d;
    },
    { refetchOnFocus: true },
  );
  // Silent reload (no full-screen loader flash) for post-mount refreshes.
  const load = useCallback(() => refetch({ silent: true }), [refetch]);

  const handleEventLogged = useCallback((eventType: string) => {
    // Refresh relevant data when events are logged
    if (eventType === 'water') {
      setHydrationRefresh(prev => prev + 1);
    }
    if (eventType === 'meal') {
      setMealRefresh(prev => prev + 1);
    }
    if (eventType === 'activity') {
      setActivityRefresh(prev => prev + 1);
    }
    if (eventType === 'medication') {
      setMedicationRefresh(prev => prev + 1);
    }
    setSummaryRefresh(prev => prev + 1);
    // Refresh main dashboard data for other event types
    load();
  }, [load]);

  async function startPeriod() {
    Alert.alert("Start period today?", "This logs a new period starting today.", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Start",
        onPress: async () => {
          await api.post("/cycles", { start_date: todayISO() });
          load();
        },
      },
    ]);
  }

  function onAction(key: string) {
    if (key === "period") startPeriod();
    else router.push(`/log?focus=${key}`);
  }

  const p = data?.prediction;
  const { phase, sub } = currentPhaseLabel(p);
  const greetName = user?.full_name || data?.user?.full_name || "there";
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";

  if (loading) {
    return (
      <View style={styles.loader} testID="dashboard-loading">
        <ActivityIndicator size="large" color={colors.brand.primary} />
      </View>
    );
  }

  return (
    <View style={styles.screen}>
      <ScrollView
        testID="dashboard-screen"
        style={styles.scrollView}
        contentContainerStyle={{ paddingBottom: 120 }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={async () => {
              setRefreshing(true);
              setHydrationRefresh(prev => prev + 1);
              setMealRefresh(prev => prev + 1);
              setActivityRefresh(prev => prev + 1);
              setMedicationRefresh(prev => prev + 1);
              await refetch({ silent: true });
              setRefreshing(false);
            }}
            tintColor={colors.brand.primary}
          />
        }
      >
        <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
          <View style={{ flex: 1 }}>
            <Text style={styles.greeting}>{greeting},</Text>
            <Text style={styles.name}>{greetName}</Text>
            <Text style={styles.date}>{formatLong(todayISO())}</Text>
          </View>
          <TouchableOpacity
            testID="open-settings-button"
            onPress={() => router.push("/settings")}
            style={styles.settingsBtn}
          >
            <Ionicons name="settings-outline" size={22} color={colors.text.secondary} />
          </TouchableOpacity>
        </View>

        <SyncStatusBar />

        <View style={styles.ringWrap}>
          <Image source={{ uri: media.cycleRingBg }} style={styles.ringBg} contentFit="contain" />
          <CycleRing
            cycleDay={p?.cycle_day && p.cycle_day > 0 ? p.cycle_day : 0}
            cycleLength={p?.avg_cycle_length || 28}
            phaseLabel={phase}
            subLabel={sub}
          />
        </View>

        {p?.has_data ? (
          <View style={styles.statsRow}>
            <Card style={styles.statCard} testID="stat-next-period">
              <Ionicons name="water-outline" size={18} color={colors.status.periodActive} />
              <Text style={styles.statValue}>{formatNice(p.next_period_date)}</Text>
              <Text style={styles.statLabel}>Next period</Text>
            </Card>
            <Card style={styles.statCard} testID="stat-fertile">
              <Ionicons name="leaf-outline" size={18} color={colors.status.fertile} />
              <Text style={styles.statValue}>{formatNice(p.fertile_window_start)}</Text>
              <Text style={styles.statLabel}>Fertile from</Text>
            </Card>
            <Card style={styles.statCard} testID="stat-ovulation">
              <Ionicons name="ellipse-outline" size={18} color={colors.brand.primary} />
              <Text style={styles.statValue}>{formatNice(p.ovulation_date)}</Text>
              <Text style={styles.statLabel}>Ovulation</Text>
            </Card>
          </View>
        ) : (
          <Card style={styles.emptyCard} highlight testID="dashboard-empty-state">
            <Text style={styles.emptyTitle}>Start tracking your cycle</Text>
            <Text style={styles.emptyText}>
              Log your period start to unlock predictions and insights.
            </Text>
          </Card>
        )}

        {/* Today at a glance — Daily Summary Engine */}
        <Text style={styles.sectionLabel}>Today at a glance</Text>
        <DailySummaryCard refreshTrigger={summaryRefresh} />

        {/* Hydration Widget */}
        <Text style={styles.sectionLabel}>Today&apos;s hydration</Text>
        <View style={styles.widgetContainer}>
          <HydrationWidget 
            onLogWater={() => {}} 
            onLogged={() => setSummaryRefresh(prev => prev + 1)}
            refreshTrigger={hydrationRefresh}
          />
        </View>

        {/* Meal Widget */}
        <Text style={styles.sectionLabel}>Today&apos;s meals</Text>
        <View style={styles.widgetContainer}>
          <MealWidget 
            onLogMeal={() => {}} 
            refreshTrigger={mealRefresh}
          />
        </View>

        {/* Sexual Activity Widget */}
        <Text style={styles.sectionLabel}>Intimacy tracking</Text>
        <View style={styles.widgetContainer}>
          <SexualActivityWidget 
            onLogActivity={() => {}} 
            refreshTrigger={activityRefresh}
          />
        </View>

        {/* Medication Widget */}
        <Text style={styles.sectionLabel}>Medications</Text>
        <View style={styles.widgetContainer}>
          <MedicationWidget 
            onLogMedication={() => {}} 
            refreshTrigger={medicationRefresh}
          />
        </View>

        <Text style={styles.sectionLabel}>Quick log</Text>
        <View style={styles.actionsRow}>
          {QUICK_ACTIONS.map((a) => (
            <TouchableOpacity
              key={a.key}
              testID={`dashboard-quick-log-${a.key}`}
              activeOpacity={0.7}
              style={styles.actionCard}
              onPress={() => onAction(a.key)}
            >
              <View style={[styles.actionIcon, { backgroundColor: a.color + "1A" }]}>
                <Ionicons name={a.icon as any} size={24} color={a.color} />
              </View>
              <Text style={styles.actionLabel}>{a.label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {data?.today_log &&
        (data.today_log.symptoms?.length || data.today_log.moods?.length || data.today_log.note) ? (
          <Card style={{ marginHorizontal: spacing.screen, marginTop: spacing.md }} testID="today-summary">
            <Text style={styles.sectionLabelInline}>Today&apos;s log</Text>
            {data.today_log.moods?.length ? (
              <Text style={styles.summaryText}>
                Moods: {data.today_log.moods.join(", ")}
              </Text>
            ) : null}
            {data.today_log.symptoms?.length ? (
              <Text style={styles.summaryText}>
                Symptoms:{" "}
                {data.today_log.symptoms.map((s: any) => `${s.name} (${s.severity})`).join(", ")}
              </Text>
            ) : null}
            {data.today_log.note ? (
              <Text style={styles.summaryText}>Note: {data.today_log.note}</Text>
            ) : null}
          </Card>
        ) : null}

        <View style={styles.disclaimerRow}>
          <Ionicons name="information-circle-outline" size={14} color={colors.text.tertiary} />
          <Text style={styles.disclaimer}>{PREDICTION_DISCLAIMER}</Text>
        </View>
      </ScrollView>

      {/* Quick Capture FAB + Bottom Sheets */}
      <QuickCaptureOverlay onEventLogged={handleEventLogged} />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg.primary },
  loader: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.bg.primary },
  header: {
    flexDirection: "row",
    alignItems: "flex-start",
    paddingHorizontal: spacing.screen,
    paddingBottom: spacing.md,
  },
  greeting: { ...type.body, color: colors.text.secondary },
  name: { ...type.h1, color: colors.text.primary },
  date: { ...type.bodySm, color: colors.text.tertiary, marginTop: 2 },
  settingsBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.bg.secondary,
    alignItems: "center",
    justifyContent: "center",
  },
  ringWrap: { alignItems: "center", justifyContent: "center", marginVertical: spacing.lg },
  ringBg: { position: "absolute", width: 300, height: 300, opacity: 0.5 },
  statsRow: { flexDirection: "row", paddingHorizontal: spacing.screen, gap: spacing.sm },
  statCard: { flex: 1, padding: spacing.md, alignItems: "flex-start" },
  statValue: { ...type.h3, color: colors.text.primary, marginTop: spacing.sm },
  statLabel: { ...type.bodySm, color: colors.text.tertiary },
  emptyCard: { marginHorizontal: spacing.screen },
  emptyTitle: { ...type.h3, color: colors.text.primary },
  emptyText: { ...type.body, color: colors.text.secondary, marginTop: spacing.xs },
  sectionLabel: {
    ...type.caption,
    color: colors.text.tertiary,
    marginTop: spacing.xl,
    marginBottom: spacing.md,
    paddingHorizontal: spacing.screen,
  },
  sectionLabelInline: { ...type.caption, color: colors.text.tertiary, marginBottom: spacing.sm },
  actionsRow: { flexDirection: "row", paddingHorizontal: spacing.screen, gap: spacing.sm },
  actionCard: {
    flex: 1,
    backgroundColor: colors.bg.primary,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.ui.border,
    padding: spacing.md,
    alignItems: "center",
  },
  actionIcon: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.sm,
  },
  actionLabel: { ...type.bodySm, color: colors.text.primary, fontWeight: "600", textAlign: "center" },
  summaryText: { ...type.body, color: colors.text.secondary, marginTop: 4 },
  disclaimerRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    marginTop: spacing.xl,
    paddingHorizontal: spacing.screen,
  },
  disclaimer: { ...type.bodySm, color: colors.text.tertiary, marginLeft: 6, textAlign: "center" },
});
