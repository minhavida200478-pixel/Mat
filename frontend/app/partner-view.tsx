import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Alert, Platform, ScrollView, Text, TouchableOpacity, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api/client";
import { PREDICTION_DISCLAIMER } from "@/src/constants";
import { useFetch } from "@/src/hooks/useFetch";
import notificationService from "@/src/services/notifications";
import {
  applyPartnerReminders,
  getPartnerReminders,
  PartnerReminderPrefs,
  savePartnerReminders,
} from "@/src/services/partnerReminders";
import { colors, spacing } from "@/src/theme";
import { todayISO } from "@/src/utils/cycle";

import { RANGES, RangeKey, shiftISO, styles, timeAgo, ViewData } from "@/src/components/partner/shared";
import {
  CalendarSection,
  CareSection,
  CycleAwarenessSection,
  DigestSection,
  EmergencyBanner,
  IntimacySection,
  LogsSection,
  OverviewSection,
  PermissionsSection,
  RemindersSection,
  SharedSpaceCta,
  SymptomTrendsSection,
  TimelineSection,
  TodaySection,
  WeeklySummarySection,
} from "@/src/components/partner/sections";

export default function PartnerView() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const params = useLocalSearchParams<{ id?: string; name?: string }>();
  const linkId = params.id || "";

  const [range, setRange] = useState<RangeKey>("week");
  const [calMonth, setCalMonth] = useState(() => new Date());
  const [reminders, setReminders] = useState<PartnerReminderPrefs>({
    period: false,
    hydration: false,
    medication: false,
  });

  const { data, loading, error } = useFetch<ViewData>(
    () => api.get<ViewData>(`/partner/view/${linkId}`),
    { deps: [linkId] },
  );

  useEffect(() => {
    getPartnerReminders(linkId).then(setReminders);
  }, [linkId]);

  const p = data?.prediction;
  const cal = data?.calendar;

  const calSets = useMemo(() => {
    return {
      period: new Set(cal?.period_days || []),
      predicted: new Set(cal?.predicted_period_days || []),
      fertile: new Set(cal?.fertile_days || []),
      note: new Set(cal?.note_days || []),
      symptom: new Set(cal?.symptom_days || []),
      ovulation: cal?.ovulation_day || null,
    };
  }, [cal]);

  const filteredTimeline = useMemo(() => {
    const items = data?.timeline || [];
    const today = todayISO();
    const rangeDef = RANGES.find((r) => r.key === range)!;
    const cutoff = shiftISO(today, -rangeDef.days);
    return items.filter((it) => it.date >= cutoff && it.date <= today);
  }, [data?.timeline, range]);

  const toggleReminder = useCallback(
    async (key: keyof PartnerReminderPrefs) => {
      const turningOn = !reminders[key];
      if (turningOn && Platform.OS !== "web") {
        const granted = await notificationService.requestPermissions();
        if (!granted) {
          Alert.alert(
            "Notifications off",
            "Enable notifications in Settings to receive partner reminders.",
            [{ text: "OK" }],
          );
          return;
        }
      }
      const next = { ...reminders, [key]: turningOn };
      setReminders(next);
      await savePartnerReminders(linkId, next);
      if (turningOn) {
        const labels: Record<string, string> = {
          period: "Period reminder enabled",
          hydration: "Hydration reminder enabled",
          medication: "Medication reminder enabled",
        };
        api.post(`/partner/${linkId}/support`, { kind: `reminder_${key}`, label: labels[key] }).catch(() => {});
      }
      await applyPartnerReminders(linkId, next, {
        name: data?.owner_name || params.name || "your partner",
        daysUntilPeriod: p?.days_until_next_period ?? null,
        hydrationPct: data?.hydration?.percentage ?? null,
      });
    },
    [reminders, linkId, data, p, params.name],
  );

  const openSpace = useCallback(() => {
    router.push({
      pathname: "/partner-space",
      params: { id: linkId, name: (data?.owner_name || "").split(" ")[0] },
    });
  }, [router, linkId, data?.owner_name]);

  return (
    <View style={styles.screen} testID="partner-view-screen">
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <TouchableOpacity testID="partner-view-back" onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.text.primary} />
        </TouchableOpacity>
        <View>
          <Text style={styles.headerTitle}>{data?.owner_name || params.name || "Partner"}</Text>
          <View style={styles.readonlyBadge}>
            <Ionicons name="eye-outline" size={12} color={colors.brand.primary} />
            <Text style={styles.readonlyText}>Read-only · Updated {timeAgo(data?.last_updated)}</Text>
          </View>
        </View>
      </View>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={colors.brand.primary} />
        </View>
      ) : error ? (
        <View style={styles.center}>
          <Ionicons name="lock-closed-outline" size={40} color={colors.text.tertiary} />
          <Text style={styles.errorText}>{error}</Text>
        </View>
      ) : data ? (
        <ScrollView contentContainerStyle={{ padding: spacing.screen, paddingBottom: spacing.xxl }}>
          <EmergencyBanner data={data} />
          <SharedSpaceCta onPress={openSpace} />
          {p ? <OverviewSection p={p} flags={data.flags} /> : null}
          <CareSection suggestions={data.care_suggestions} />
          <CycleAwarenessSection awareness={data.cycle_awareness} />
          <SymptomTrendsSection trends={data.symptom_trends} />
          <DigestSection digest={data.digest} />
          <WeeklySummarySection summary={data.weekly_summary} />
          <CalendarSection cal={cal} calSets={calSets} calMonth={calMonth} setCalMonth={setCalMonth} />
          <TodaySection hydration={data.hydration} meals={data.meals} medications={data.medications} />
          <TimelineSection
            timeline={data.timeline}
            filteredTimeline={filteredTimeline}
            range={range}
            setRange={setRange}
          />
          <IntimacySection intimacy={data.intimacy} />
          <RemindersSection reminders={reminders} onToggle={toggleReminder} />
          <PermissionsSection flags={data.flags} />
          <LogsSection logs={data.logs} />

          <Text style={styles.disclaimer}>{PREDICTION_DISCLAIMER}</Text>
        </ScrollView>
      ) : null}
    </View>
  );
}
