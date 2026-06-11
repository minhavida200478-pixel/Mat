import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Platform,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api/client";
import { colors, radius, spacing, type } from "@/src/theme";
import { todayISO } from "@/src/utils/cycle";
import { notificationService } from "@/src/services/notifications";
import { syncWrite } from "@/src/sync/offlineQueue";
import ScheduleForm from "@/src/components/medications/ScheduleForm";
import {
  ACCENT,
  Adherence,
  Dose,
  Schedule,
  TodayData,
  adherenceColor,
  catIcon,
  fmtTime,
  scheduleSummary,
} from "@/src/components/medications/types";

// Memoized dose row — avoids re-rendering every dose when only one changes.
const DoseRow = React.memo(function DoseRow({
  dose,
  index,
  isLast,
  onTake,
}: {
  dose: Dose;
  index: number;
  isLast: boolean;
  onTake: (d: Dose) => void;
}) {
  return (
    <View testID={`dose-row-${index}`} style={[styles.doseRow, !isLast && styles.rowBorder]}>
      <View style={[styles.doseIcon, { backgroundColor: ACCENT + "15" }]}>
        <Ionicons name={catIcon(dose.category) as any} size={18} color={ACCENT} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={[styles.doseName, dose.taken && styles.doseNameTaken]}>{dose.name}</Text>
        <Text style={styles.doseMeta}>
          {fmtTime(dose.time)}
          {dose.dosage ? ` · ${dose.dosage}` : ""}
        </Text>
      </View>
      {dose.taken ? (
        <View style={styles.takenPill}>
          <Ionicons name="checkmark" size={14} color={colors.status.success} />
          <Text style={styles.takenPillText}>Taken</Text>
        </View>
      ) : (
        <TouchableOpacity
          testID={`dose-take-${index}`}
          style={styles.takeBtn}
          onPress={() => onTake(dose)}
          activeOpacity={0.8}
        >
          <Text style={styles.takeBtnText}>Mark taken</Text>
        </TouchableOpacity>
      )}
    </View>
  );
});

// Memoized schedule card.
const ScheduleCard = React.memo(function ScheduleCard({
  schedule,
  onToggle,
  onEdit,
  onDelete,
}: {
  schedule: Schedule;
  onToggle: (s: Schedule) => void;
  onEdit: (s: Schedule) => void;
  onDelete: (s: Schedule) => void;
}) {
  return (
    <View style={styles.schedCard} testID={`schedule-${schedule.id}`}>
      <View style={styles.schedHeader}>
        <View style={[styles.doseIcon, { backgroundColor: ACCENT + "15" }]}>
          <Ionicons name={catIcon(schedule.category) as any} size={18} color={ACCENT} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.schedName}>{schedule.name}</Text>
          <Text style={styles.schedMeta}>
            {schedule.dosage ? `${schedule.dosage} · ` : ""}
            {scheduleSummary(schedule)}
          </Text>
        </View>
        <Switch
          testID={`schedule-toggle-${schedule.id}`}
          value={schedule.enabled}
          onValueChange={() => onToggle(schedule)}
          trackColor={{ true: ACCENT, false: colors.ui.border }}
          thumbColor="#fff"
        />
      </View>
      <View style={styles.schedTimes}>
        {schedule.times.map((t) => (
          <View key={t} style={styles.timePill}>
            <Ionicons name="time-outline" size={12} color={colors.text.secondary} />
            <Text style={styles.timePillText}>{fmtTime(t)}</Text>
          </View>
        ))}
      </View>
      <View style={styles.schedActions}>
        <TouchableOpacity testID={`schedule-edit-${schedule.id}`} style={styles.linkBtn} onPress={() => onEdit(schedule)}>
          <Ionicons name="create-outline" size={16} color={colors.text.secondary} />
          <Text style={styles.linkText}>Edit</Text>
        </TouchableOpacity>
        <TouchableOpacity testID={`schedule-delete-${schedule.id}`} style={styles.linkBtn} onPress={() => onDelete(schedule)}>
          <Ionicons name="trash-outline" size={16} color={colors.status.periodActive} />
          <Text style={[styles.linkText, { color: colors.status.periodActive }]}>Delete</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
});

export default function MedicationsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [today, setToday] = useState<TodayData | null>(null);
  const [adherence, setAdherence] = useState<Adherence | null>(null);

  const [formVisible, setFormVisible] = useState(false);
  const [editing, setEditing] = useState<Schedule | null>(null);

  const load = useCallback(async () => {
    try {
      const [sch, td, adh] = await Promise.all([
        api.get<Schedule[]>("/medication-schedules"),
        api.get<TodayData>(`/medication-schedules/today?today=${todayISO()}`),
        api.get<Adherence>(`/medication-schedules/adherence?days=30&today=${todayISO()}`),
      ]);
      setSchedules(sch);
      setToday(td);
      setAdherence(adh);
      // Keep native reminders in sync (no-op on web / Expo Go).
      notificationService.syncMedicationReminders(sch).catch(() => {});
    } catch (e) {
      console.error("Failed to load medications:", e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const onTake = useCallback(
    async (dose: Dose) => {
      if (dose.taken) return;
      if (Platform.OS !== "web") Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
      // optimistic
      setToday((prev) =>
        prev
          ? {
              ...prev,
              taken: prev.taken + 1,
              pending: prev.pending - 1,
              doses: prev.doses.map((d) =>
                d.schedule_id === dose.schedule_id && d.time === dose.time ? { ...d, taken: true } : d,
              ),
            }
          : prev,
      );
      try {
        const res = await syncWrite(
          "POST",
          `/medication-schedules/${dose.schedule_id}/take`,
          { scheduled_time: dose.time, timestamp: new Date().toISOString() },
          `Took ${dose.name}`,
        );
        if (!res.queued) {
          const adh = await api.get<Adherence>(
            `/medication-schedules/adherence?days=30&today=${todayISO()}`,
          );
          setAdherence(adh);
        }
      } catch (e) {
        console.error("Failed to mark taken:", e);
        load();
      }
    },
    [load],
  );

  const onToggleEnabled = useCallback(
    async (sched: Schedule) => {
      const updated = { ...sched, enabled: !sched.enabled };
      setSchedules((prev) => prev.map((s) => (s.id === sched.id ? updated : s)));
      try {
        await api.put(`/medication-schedules/${sched.id}`, {
          name: sched.name,
          dosage: sched.dosage,
          category: sched.category,
          schedule_type: sched.schedule_type,
          times: sched.times,
          interval_hours: sched.interval_hours,
          interval_start: sched.interval_start,
          cycle_days: sched.cycle_days,
          enabled: updated.enabled,
        });
        load();
      } catch (e) {
        console.error("Failed to toggle:", e);
        load();
      }
    },
    [load],
  );

  const onDelete = useCallback(
    (sched: Schedule) => {
      Alert.alert("Delete medication?", `Remove "${sched.name}" and its reminders.`, [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete",
          style: "destructive",
          onPress: async () => {
            try {
              await api.del(`/medication-schedules/${sched.id}`);
              load();
            } catch (e) {
              console.error("Failed to delete:", e);
            }
          },
        },
      ]);
    },
    [load],
  );

  const openAdd = () => {
    setEditing(null);
    setFormVisible(true);
  };
  const openEdit = useCallback((s: Schedule) => {
    setEditing(s);
    setFormVisible(true);
  }, []);

  const onSaved = useCallback(() => {
    setFormVisible(false);
    setEditing(null);
    load();
  }, [load]);

  if (loading) {
    return (
      <View style={styles.loader} testID="medications-loading">
        <ActivityIndicator size="large" color={ACCENT} />
      </View>
    );
  }

  return (
    <View style={styles.screen}>
      <View style={[styles.topbar, { paddingTop: insets.top + spacing.sm }]}>
        <TouchableOpacity testID="medications-back" onPress={() => router.back()} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.text.primary} />
        </TouchableOpacity>
        <Text style={styles.topTitle}>Medications</Text>
        <TouchableOpacity testID="medications-add-top" onPress={openAdd} style={styles.iconBtn}>
          <Ionicons name="add" size={26} color={ACCENT} />
        </TouchableOpacity>
      </View>

      <ScrollView
        testID="medications-screen"
        contentContainerStyle={{ paddingBottom: insets.bottom + 100 }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => {
              setRefreshing(true);
              load();
            }}
            tintColor={ACCENT}
          />
        }
      >
        {/* Adherence summary */}
        {adherence?.has_data ? (
          <View style={styles.adherenceCard} testID="adherence-card">
            <View style={styles.adherenceTop}>
              <View>
                <Text style={styles.adherenceLabel}>30-DAY ADHERENCE</Text>
                <Text style={[styles.adherenceBig, { color: adherenceColor(adherence.overall_percentage) }]}>
                  {adherence.overall_percentage ?? 0}%
                </Text>
                <Text style={styles.adherenceSub}>
                  {adherence.taken_total} of {adherence.expected_total} doses taken
                </Text>
              </View>
              <View style={styles.streakBox}>
                <Ionicons name="flame" size={20} color="#E0712F" />
                <Text style={styles.streakNum}>{adherence.streak_days}</Text>
                <Text style={styles.streakLabel}>day streak</Text>
              </View>
            </View>
            <View style={styles.barsRow}>
              {adherence.recent.map((r) => {
                const h = r.percentage === null ? 6 : Math.max(6, Math.round((r.percentage / 100) * 44));
                const dow = new Date(r.date + "T00:00:00").toLocaleDateString([], { weekday: "narrow" });
                return (
                  <View key={r.date} style={styles.barCol}>
                    <View style={styles.barTrack}>
                      <View
                        style={[
                          styles.barFill,
                          { height: h, backgroundColor: r.percentage === null ? colors.ui.border : adherenceColor(r.percentage) },
                        ]}
                      />
                    </View>
                    <Text style={styles.barLabel}>{dow}</Text>
                  </View>
                );
              })}
            </View>
          </View>
        ) : (
          <View style={styles.adherenceCard} testID="adherence-empty">
            <Text style={styles.emptyTitle}>Track your adherence</Text>
            <Text style={styles.emptyText}>
              Add a medication with a schedule and mark doses as taken to build your adherence stats and streak.
            </Text>
          </View>
        )}

        {/* Today's doses */}
        <Text style={styles.sectionLabel}>Today&apos;s doses</Text>
        {today && today.doses.length > 0 ? (
          <View style={styles.card}>
            {today.doses.map((d, i) => (
              <DoseRow
                key={`${d.schedule_id}-${d.time}`}
                dose={d}
                index={i}
                isLast={i === today.doses.length - 1}
                onTake={onTake}
              />
            ))}
          </View>
        ) : (
          <View style={styles.card}>
            <Text style={styles.emptyText}>No doses scheduled for today.</Text>
          </View>
        )}

        {/* Schedules */}
        <Text style={styles.sectionLabel}>Your medications</Text>
        {schedules.length === 0 ? (
          <View style={styles.card}>
            <Text style={styles.emptyText}>No medications yet. Tap “Add medication” to set up reminders.</Text>
          </View>
        ) : (
          schedules.map((s) => (
            <ScheduleCard
              key={s.id}
              schedule={s}
              onToggle={onToggleEnabled}
              onEdit={openEdit}
              onDelete={onDelete}
            />
          ))
        )}

        {Platform.OS !== "web" && schedules.length > 0 && (
          <View style={styles.noteRow}>
            <Ionicons name="information-circle-outline" size={14} color={colors.text.tertiary} />
            <Text style={styles.noteText}>
              Reminder notifications fire on a development/production build, not in Expo Go.
            </Text>
          </View>
        )}
      </ScrollView>

      <View style={[styles.fabWrap, { paddingBottom: insets.bottom + spacing.md }]}>
        <TouchableOpacity testID="medications-add" style={styles.fab} onPress={openAdd} activeOpacity={0.85}>
          <Ionicons name="add" size={20} color="#fff" />
          <Text style={styles.fabText}>Add medication</Text>
        </TouchableOpacity>
      </View>

      <ScheduleForm
        visible={formVisible}
        editing={editing}
        onClose={() => {
          setFormVisible(false);
          setEditing(null);
        }}
        onSaved={onSaved}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg.secondary },
  loader: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.bg.primary },
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

  adherenceCard: {
    backgroundColor: colors.bg.primary,
    margin: spacing.screen,
    marginBottom: 0,
    borderRadius: radius.lg,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.ui.border,
  },
  adherenceTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  adherenceLabel: { ...type.caption, color: colors.text.tertiary },
  adherenceBig: { fontSize: 44, fontWeight: "800", letterSpacing: -1, marginTop: 2 },
  adherenceSub: { ...type.bodySm, color: colors.text.secondary },
  streakBox: { alignItems: "center", backgroundColor: "#FFF3EC", borderRadius: radius.md, paddingVertical: spacing.sm, paddingHorizontal: spacing.md },
  streakNum: { ...type.h2, color: "#E0712F", marginTop: 2 },
  streakLabel: { ...type.caption, color: "#B05B25", textTransform: "none" },
  barsRow: { flexDirection: "row", justifyContent: "space-between", marginTop: spacing.lg, alignItems: "flex-end" },
  barCol: { alignItems: "center", flex: 1 },
  barTrack: { height: 44, width: 10, backgroundColor: colors.bg.tertiary, borderRadius: 5, justifyContent: "flex-end", overflow: "hidden" },
  barFill: { width: 10, borderRadius: 5 },
  barLabel: { ...type.caption, color: colors.text.tertiary, marginTop: 4, textTransform: "none" },

  sectionLabel: {
    ...type.caption,
    color: colors.text.tertiary,
    marginTop: spacing.xl,
    marginBottom: spacing.sm,
    paddingHorizontal: spacing.screen,
  },
  card: {
    backgroundColor: colors.bg.primary,
    marginHorizontal: spacing.screen,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.ui.border,
    padding: spacing.md,
  },
  emptyTitle: { ...type.h3, color: colors.text.primary, marginBottom: spacing.xs },
  emptyText: { ...type.body, color: colors.text.secondary },

  doseRow: { flexDirection: "row", alignItems: "center", paddingVertical: spacing.sm },
  rowBorder: { borderBottomWidth: 1, borderBottomColor: colors.ui.divider },
  doseIcon: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center", marginRight: spacing.md },
  doseName: { ...type.body, color: colors.text.primary, fontWeight: "600" },
  doseNameTaken: { textDecorationLine: "line-through", color: colors.text.tertiary },
  doseMeta: { ...type.bodySm, color: colors.text.secondary, marginTop: 1 },
  takeBtn: { backgroundColor: ACCENT, paddingVertical: 8, paddingHorizontal: spacing.md, borderRadius: radius.pill },
  takeBtnText: { color: "#fff", fontWeight: "600", fontSize: 13 },
  takenPill: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.status.success + "18", paddingVertical: 6, paddingHorizontal: spacing.sm, borderRadius: radius.pill },
  takenPillText: { color: colors.status.success, fontWeight: "600", fontSize: 12 },

  schedCard: {
    backgroundColor: colors.bg.primary,
    marginHorizontal: spacing.screen,
    marginBottom: spacing.sm,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.ui.border,
    padding: spacing.md,
  },
  schedHeader: { flexDirection: "row", alignItems: "center" },
  schedName: { ...type.body, color: colors.text.primary, fontWeight: "700" },
  schedMeta: { ...type.bodySm, color: colors.text.secondary, marginTop: 1 },
  schedTimes: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs, marginTop: spacing.sm },
  timePill: { flexDirection: "row", alignItems: "center", gap: 3, backgroundColor: colors.bg.secondary, paddingVertical: 4, paddingHorizontal: spacing.sm, borderRadius: radius.pill },
  timePillText: { ...type.caption, color: colors.text.secondary, textTransform: "none" },
  schedActions: { flexDirection: "row", gap: spacing.lg, marginTop: spacing.md, borderTopWidth: 1, borderTopColor: colors.ui.divider, paddingTop: spacing.sm },
  linkBtn: { flexDirection: "row", alignItems: "center", gap: 4 },
  linkText: { ...type.bodySm, color: colors.text.secondary, fontWeight: "600" },

  noteRow: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: spacing.screen, marginTop: spacing.md },
  noteText: { ...type.bodySm, color: colors.text.tertiary, flex: 1 },

  fabWrap: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: spacing.screen, backgroundColor: "transparent" },
  fab: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.xs,
    backgroundColor: ACCENT,
    paddingVertical: spacing.md,
    borderRadius: radius.pill,
    elevation: 4,
    ...Platform.select({
      web: { boxShadow: "0px 4px 10px rgba(0,0,0,0.18)" },
      default: {
        shadowColor: "#000",
        shadowOpacity: 0.18,
        shadowRadius: 10,
        shadowOffset: { width: 0, height: 4 },
      },
    }),
  },
  fabText: { color: "#fff", fontWeight: "700", fontSize: 16 },
});
