// Add / Edit medication schedule form — extracted from app/medications.tsx.
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import React, { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Modal,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api/client";
import { colors, radius, spacing, type } from "@/src/theme";
import {
  ACCENT,
  CATEGORIES,
  COMMON_TIMES,
  INTERVAL_OPTIONS,
  Schedule,
  ScheduleType,
  fmtTime,
} from "./types";

export default function ScheduleForm({
  visible,
  editing,
  onClose,
  onSaved,
}: {
  visible: boolean;
  editing: Schedule | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const insets = useSafeAreaInsets();
  const [name, setName] = useState("");
  const [dosage, setDosage] = useState("");
  const [category, setCategory] = useState("other");
  const [scheduleType, setScheduleType] = useState<ScheduleType>("daily");
  const [times, setTimes] = useState<string[]>(["09:00"]);
  const [intervalHours, setIntervalHours] = useState<number>(8);
  const [intervalStart, setIntervalStart] = useState<string>("08:00");
  const [cycleDays, setCycleDays] = useState<number[]>([]);
  const [customTime, setCustomTime] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!visible) return;
    if (editing) {
      setName(editing.name);
      setDosage(editing.dosage ?? "");
      setCategory(editing.category);
      setScheduleType(editing.schedule_type);
      setTimes(editing.times.length ? editing.times : ["09:00"]);
      setIntervalHours(editing.interval_hours ?? 8);
      setIntervalStart(editing.interval_start ?? "08:00");
      setCycleDays(editing.cycle_days ?? []);
    } else {
      setName("");
      setDosage("");
      setCategory("other");
      setScheduleType("daily");
      setTimes(["09:00"]);
      setIntervalHours(8);
      setIntervalStart("08:00");
      setCycleDays([]);
    }
    setCustomTime("");
    setError(null);
  }, [visible, editing]);

  const toggleTime = (t: string) =>
    setTimes((prev) => (prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t].sort()));

  const addCustomTime = () => {
    const m = customTime.match(/^([01]?\d|2[0-3]):([0-5]\d)$/);
    if (!m) {
      setError("Custom time must be in 24h HH:MM format (e.g. 07:30).");
      return;
    }
    const norm = `${m[1].padStart(2, "0")}:${m[2]}`;
    if (!times.includes(norm)) setTimes((prev) => [...prev, norm].sort());
    setCustomTime("");
    setError(null);
  };

  const toggleCycleDay = (d: number) =>
    setCycleDays((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d].sort((a, b) => a - b)));

  const intervalPreview = useMemo(() => {
    const [h, mm] = intervalStart.split(":").map((x) => parseInt(x, 10));
    let cur = h * 60 + (mm || 0);
    const out: string[] = [];
    while (cur < 24 * 60 && out.length < 24) {
      out.push(`${String(Math.floor(cur / 60)).padStart(2, "0")}:${String(cur % 60).padStart(2, "0")}`);
      cur += intervalHours * 60;
    }
    return out;
  }, [intervalStart, intervalHours]);

  const save = async () => {
    setError(null);
    if (!name.trim()) {
      setError("Please enter a medication name.");
      return;
    }
    if (scheduleType !== "interval" && times.length === 0) {
      setError("Add at least one time.");
      return;
    }
    if (scheduleType === "cycle_based" && cycleDays.length === 0) {
      setError("Select at least one cycle day.");
      return;
    }
    setSaving(true);
    const body = {
      name: name.trim(),
      dosage: dosage.trim() || undefined,
      category,
      schedule_type: scheduleType,
      times: scheduleType === "interval" ? [] : times,
      interval_hours: scheduleType === "interval" ? intervalHours : undefined,
      interval_start: scheduleType === "interval" ? intervalStart : undefined,
      cycle_days: scheduleType === "cycle_based" ? cycleDays : [],
      enabled: editing ? editing.enabled : true,
    };
    try {
      if (editing) await api.put(`/medication-schedules/${editing.id}`, body);
      else await api.post("/medication-schedules", body);
      if (Platform.OS !== "web") Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      onSaved();
    } catch (e: any) {
      setError(e?.message || "Could not save. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent={false} onRequestClose={onClose}>
      <View style={[styles.formScreen, { paddingTop: insets.top }]}>
        <View style={styles.formHeader}>
          <TouchableOpacity testID="form-cancel" onPress={onClose} style={styles.iconBtn}>
            <Ionicons name="close" size={24} color={colors.text.primary} />
          </TouchableOpacity>
          <Text style={styles.topTitle}>{editing ? "Edit medication" : "Add medication"}</Text>
          <View style={styles.iconBtn} />
        </View>

        <KeyboardAwareScrollView
          contentContainerStyle={{ padding: spacing.screen, paddingBottom: 140 }}
          bottomOffset={20}
          keyboardShouldPersistTaps="handled"
        >
          <Text style={styles.label}>Name *</Text>
          <TextInput
            testID="form-name"
            style={styles.input}
            placeholder="e.g. Ibuprofen, Vitamin D"
            placeholderTextColor={colors.text.tertiary}
            value={name}
            onChangeText={setName}
          />

          <Text style={styles.label}>Dosage (optional)</Text>
          <TextInput
            testID="form-dosage"
            style={styles.input}
            placeholder="e.g. 400mg, 1 tablet"
            placeholderTextColor={colors.text.tertiary}
            value={dosage}
            onChangeText={setDosage}
          />

          <Text style={styles.label}>Category</Text>
          <View style={styles.wrapRow}>
            {CATEGORIES.map((c) => (
              <TouchableOpacity
                key={c.key}
                testID={`form-cat-${c.key}`}
                style={[styles.chip, category === c.key && styles.chipActive]}
                onPress={() => setCategory(c.key)}
              >
                <Ionicons name={c.icon as any} size={14} color={category === c.key ? "#fff" : ACCENT} />
                <Text style={[styles.chipText, category === c.key && styles.chipTextActive]}>{c.label}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <Text style={styles.label}>Schedule</Text>
          <View style={styles.segment}>
            {([
              { k: "daily", l: "Daily" },
              { k: "interval", l: "Every X hrs" },
              { k: "cycle_based", l: "Cycle days" },
            ] as const).map((opt) => (
              <TouchableOpacity
                key={opt.k}
                testID={`form-type-${opt.k}`}
                style={[styles.segmentBtn, scheduleType === opt.k && styles.segmentBtnActive]}
                onPress={() => setScheduleType(opt.k)}
              >
                <Text style={[styles.segmentText, scheduleType === opt.k && styles.segmentTextActive]}>
                  {opt.l}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          {scheduleType === "interval" ? (
            <>
              <Text style={styles.subLabel}>Frequency</Text>
              <View style={styles.wrapRow}>
                {INTERVAL_OPTIONS.map((h) => (
                  <TouchableOpacity
                    key={h}
                    testID={`form-interval-${h}`}
                    style={[styles.chip, intervalHours === h && styles.chipActive]}
                    onPress={() => setIntervalHours(h)}
                  >
                    <Text style={[styles.chipText, intervalHours === h && styles.chipTextActive]}>
                      Every {h}h
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
              <Text style={styles.subLabel}>First dose</Text>
              <View style={styles.wrapRow}>
                {["06:00", "07:00", "08:00", "09:00"].map((t) => (
                  <TouchableOpacity
                    key={t}
                    style={[styles.chip, intervalStart === t && styles.chipActive]}
                    onPress={() => setIntervalStart(t)}
                  >
                    <Text style={[styles.chipText, intervalStart === t && styles.chipTextActive]}>{fmtTime(t)}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <Text style={styles.previewText}>
                Doses at: {intervalPreview.map(fmtTime).join(", ")}
              </Text>
            </>
          ) : (
            <>
              <Text style={styles.subLabel}>Times</Text>
              <View style={styles.wrapRow}>
                {COMMON_TIMES.map((t) => (
                  <TouchableOpacity
                    key={t}
                    testID={`form-time-${t}`}
                    style={[styles.chip, times.includes(t) && styles.chipActive]}
                    onPress={() => toggleTime(t)}
                  >
                    <Text style={[styles.chipText, times.includes(t) && styles.chipTextActive]}>{fmtTime(t)}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <View style={styles.customRow}>
                <TextInput
                  testID="form-custom-time"
                  style={[styles.input, { flex: 1, marginBottom: 0 }]}
                  placeholder="Custom HH:MM (24h)"
                  placeholderTextColor={colors.text.tertiary}
                  value={customTime}
                  onChangeText={setCustomTime}
                  keyboardType="numbers-and-punctuation"
                />
                <TouchableOpacity testID="form-add-time" style={styles.addTimeBtn} onPress={addCustomTime}>
                  <Ionicons name="add" size={20} color="#fff" />
                </TouchableOpacity>
              </View>
              {times.length > 0 && (
                <Text style={styles.previewText}>Selected: {times.map(fmtTime).join(", ")}</Text>
              )}
            </>
          )}

          {scheduleType === "cycle_based" && (
            <>
              <Text style={styles.subLabel}>On cycle days</Text>
              <View style={styles.wrapRow}>
                {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => (
                  <TouchableOpacity
                    key={d}
                    testID={`form-cycleday-${d}`}
                    style={[styles.dayChip, cycleDays.includes(d) && styles.chipActive]}
                    onPress={() => toggleCycleDay(d)}
                  >
                    <Text style={[styles.chipText, cycleDays.includes(d) && styles.chipTextActive]}>{d}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </>
          )}

          {error && (
            <View style={styles.errorRow} testID="form-error">
              <Ionicons name="alert-circle" size={16} color={colors.status.error} />
              <Text style={styles.errorText}>{error}</Text>
            </View>
          )}
        </KeyboardAwareScrollView>

        <View style={[styles.saveBar, { paddingBottom: insets.bottom + spacing.sm }]}>
          <TouchableOpacity
            testID="form-save"
            style={[styles.saveBtn, saving && { opacity: 0.6 }]}
            onPress={save}
            disabled={saving}
            activeOpacity={0.85}
          >
            {saving ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.saveBtnText}>{editing ? "Save changes" : "Add medication"}</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  formScreen: { flex: 1, backgroundColor: colors.bg.primary },
  formHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.ui.divider,
  },
  topTitle: { ...type.h3, color: colors.text.primary },
  iconBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  label: { ...type.bodySm, color: colors.text.secondary, fontWeight: "700", marginBottom: spacing.xs, marginTop: spacing.md },
  subLabel: { ...type.bodySm, color: colors.text.secondary, fontWeight: "600", marginBottom: spacing.xs, marginTop: spacing.md },
  input: {
    ...type.body,
    backgroundColor: colors.bg.secondary,
    borderRadius: radius.sm,
    padding: spacing.md,
    color: colors.text.primary,
    borderWidth: 1,
    borderColor: colors.ui.border,
    marginBottom: spacing.xs,
  },
  wrapRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  chip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    backgroundColor: ACCENT + "12",
    paddingVertical: 8,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: "transparent",
  },
  chipActive: { backgroundColor: ACCENT, borderColor: ACCENT },
  chipText: { ...type.bodySm, color: ACCENT, fontWeight: "600" },
  chipTextActive: { color: "#fff" },
  dayChip: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: ACCENT + "12",
  },
  segment: { flexDirection: "row", backgroundColor: colors.bg.secondary, borderRadius: radius.md, padding: 4, gap: 4 },
  segmentBtn: { flex: 1, paddingVertical: spacing.sm, borderRadius: radius.sm, alignItems: "center" },
  segmentBtnActive: { backgroundColor: colors.bg.primary, borderWidth: 1, borderColor: ACCENT },
  segmentText: { ...type.bodySm, color: colors.text.secondary, fontWeight: "600" },
  segmentTextActive: { color: ACCENT },
  customRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.sm },
  addTimeBtn: { width: 48, height: 48, borderRadius: radius.sm, backgroundColor: ACCENT, alignItems: "center", justifyContent: "center" },
  previewText: { ...type.bodySm, color: colors.text.tertiary, marginTop: spacing.sm },
  errorRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: spacing.md },
  errorText: { ...type.bodySm, color: colors.status.error, flex: 1 },
  saveBar: {
    paddingHorizontal: spacing.screen,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.ui.divider,
    backgroundColor: colors.bg.primary,
  },
  saveBtn: { backgroundColor: ACCENT, paddingVertical: spacing.md, borderRadius: radius.pill, alignItems: "center" },
  saveBtnText: { color: "#fff", fontWeight: "700", fontSize: 16 },
});
