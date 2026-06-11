import { Ionicons } from "@expo/vector-icons";
import React, { useEffect, useState } from "react";
import { Modal, StyleSheet, Text, TouchableOpacity, View } from "react-native";

import { colors, radius, spacing, type } from "@/src/theme";

interface Props {
  visible: boolean;
  initial?: string; // "HH:MM" 24h
  title?: string;
  onCancel: () => void;
  onConfirm: (time: string) => void;
}

function parse(initial?: string): { h: number; m: number } {
  if (initial) {
    const [hh, mm] = initial.split(":").map((x) => parseInt(x, 10));
    if (!Number.isNaN(hh) && !Number.isNaN(mm)) return { h: hh, m: mm };
  }
  return { h: 9, m: 0 };
}

/** A precise HH:MM time picker that works on web + native (12h display, 24h value). */
export default function TimePickerModal({ visible, initial, title, onCancel, onConfirm }: Props) {
  const [h24, setH24] = useState(9); // 0-23
  const [minute, setMinute] = useState(0); // 0-59

  useEffect(() => {
    if (visible) {
      const p = parse(initial);
      setH24(p.h);
      setMinute(p.m);
    }
  }, [visible, initial]);

  const isPM = h24 >= 12;
  const hour12 = h24 % 12 === 0 ? 12 : h24 % 12;

  const setHour12 = (hh: number) => {
    // keep current AM/PM, change the 12h hour
    const base = hh % 12; // 12 -> 0
    setH24(isPM ? base + 12 : base);
  };
  const stepHour = (delta: number) => setHour12(((hour12 - 1 + delta + 12) % 12) + 1);
  const stepMinute = (delta: number) => setMinute((prev) => (prev + delta + 60) % 60);
  const toggleAmPm = () => setH24((prev) => (prev >= 12 ? prev - 12 : prev + 12));

  const confirm = () => {
    const out = `${String(h24).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
    onConfirm(out);
  };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onCancel}>
      <View style={styles.backdrop}>
        <View style={styles.sheet} testID="time-picker-modal">
          <Text style={styles.title}>{title || "Set time"}</Text>

          <View style={styles.display} testID="time-picker-display">
            <Text style={styles.displayText}>
              {hour12}:{String(minute).padStart(2, "0")}
            </Text>
            <Text style={styles.ampmText}>{isPM ? "PM" : "AM"}</Text>
          </View>

          <View style={styles.steppers}>
            <Stepper
              label="Hour"
              testID="tp-hour"
              onMinus={() => stepHour(-1)}
              onPlus={() => stepHour(1)}
              value={String(hour12)}
            />
            <Stepper
              label="Minute"
              testID="tp-minute"
              onMinus={() => stepMinute(-1)}
              onPlus={() => stepMinute(1)}
              onMinus5={() => stepMinute(-5)}
              onPlus5={() => stepMinute(5)}
              value={String(minute).padStart(2, "0")}
            />
          </View>

          <View style={styles.ampmRow}>
            {(["AM", "PM"] as const).map((p) => {
              const active = (p === "PM") === isPM;
              return (
                <TouchableOpacity
                  key={p}
                  testID={`tp-${p.toLowerCase()}`}
                  style={[styles.ampmBtn, active && styles.ampmBtnActive]}
                  onPress={() => {
                    if ((p === "PM") !== isPM) toggleAmPm();
                  }}
                >
                  <Text style={[styles.ampmBtnText, active && styles.ampmBtnTextActive]}>{p}</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          <View style={styles.actions}>
            <TouchableOpacity testID="tp-cancel" style={styles.cancelBtn} onPress={onCancel}>
              <Text style={styles.cancelText}>Cancel</Text>
            </TouchableOpacity>
            <TouchableOpacity testID="tp-confirm" style={styles.confirmBtn} onPress={confirm}>
              <Text style={styles.confirmText}>Set time</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
}

function Stepper({
  label,
  value,
  onMinus,
  onPlus,
  onMinus5,
  onPlus5,
  testID,
}: {
  label: string;
  value: string;
  onMinus: () => void;
  onPlus: () => void;
  onMinus5?: () => void;
  onPlus5?: () => void;
  testID: string;
}) {
  return (
    <View style={styles.stepper}>
      <Text style={styles.stepperLabel}>{label}</Text>
      <View style={styles.stepperRow}>
        {onMinus5 && (
          <TouchableOpacity testID={`${testID}-minus5`} style={styles.smallBtn} onPress={onMinus5}>
            <Text style={styles.smallBtnText}>-5</Text>
          </TouchableOpacity>
        )}
        <TouchableOpacity testID={`${testID}-minus`} style={styles.stepBtn} onPress={onMinus}>
          <Ionicons name="remove" size={20} color={colors.brand.primary} />
        </TouchableOpacity>
        <Text style={styles.stepperValue} testID={`${testID}-value`}>{value}</Text>
        <TouchableOpacity testID={`${testID}-plus`} style={styles.stepBtn} onPress={onPlus}>
          <Ionicons name="add" size={20} color={colors.brand.primary} />
        </TouchableOpacity>
        {onPlus5 && (
          <TouchableOpacity testID={`${testID}-plus5`} style={styles.smallBtn} onPress={onPlus5}>
            <Text style={styles.smallBtnText}>+5</Text>
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "center", padding: spacing.lg },
  sheet: { backgroundColor: colors.bg.primary, borderRadius: radius.lg, padding: spacing.lg },
  title: { ...type.h3, color: colors.text.primary, textAlign: "center", marginBottom: spacing.md },
  display: { flexDirection: "row", alignItems: "baseline", justifyContent: "center", gap: 6, marginBottom: spacing.lg },
  displayText: { fontSize: 48, fontWeight: "800", color: colors.text.primary, letterSpacing: -1 },
  ampmText: { ...type.h3, color: colors.brand.primary, fontWeight: "700" },
  steppers: { flexDirection: "row", justifyContent: "space-between", gap: spacing.md },
  stepper: { flex: 1, alignItems: "center" },
  stepperLabel: { ...type.caption, color: colors.text.tertiary, marginBottom: spacing.xs },
  stepperRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  stepBtn: {
    width: 40, height: 40, borderRadius: 20, backgroundColor: colors.brand.primary + "18",
    alignItems: "center", justifyContent: "center",
  },
  smallBtn: {
    width: 32, height: 32, borderRadius: 16, backgroundColor: colors.bg.secondary,
    alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.ui.border,
  },
  smallBtnText: { ...type.caption, color: colors.text.secondary, fontWeight: "700", textTransform: "none" },
  stepperValue: { ...type.h3, color: colors.text.primary, minWidth: 34, textAlign: "center" },
  ampmRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.lg },
  ampmBtn: {
    flex: 1, paddingVertical: spacing.sm, borderRadius: radius.md, alignItems: "center",
    backgroundColor: colors.bg.secondary, borderWidth: 1, borderColor: colors.ui.border,
  },
  ampmBtnActive: { backgroundColor: colors.brand.primary, borderColor: colors.brand.primary },
  ampmBtnText: { ...type.body, color: colors.text.secondary, fontWeight: "700" },
  ampmBtnTextActive: { color: "#fff" },
  actions: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.lg },
  cancelBtn: { flex: 1, paddingVertical: spacing.md, borderRadius: radius.pill, alignItems: "center", backgroundColor: colors.bg.secondary },
  cancelText: { ...type.body, color: colors.text.secondary, fontWeight: "600" },
  confirmBtn: { flex: 1, paddingVertical: spacing.md, borderRadius: radius.pill, alignItems: "center", backgroundColor: colors.brand.primary },
  confirmText: { ...type.body, color: "#fff", fontWeight: "700" },
});
