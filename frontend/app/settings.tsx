import { Ionicons } from "@expo/vector-icons";
import * as LocalAuthentication from "expo-local-authentication";
import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import {
  Alert,
  Linking,
  Platform,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api/client";
import { Card, PrimaryButton } from "@/src/components/ui";
import TimePickerModal from "@/src/components/TimePickerModal";
import { useAuth } from "@/src/ctx/AuthContext";
import { colors, radius, spacing, type } from "@/src/theme";
import { formatNice } from "@/src/utils/cycle";
import { notificationService } from "@/src/services/notifications";
import { applyReminderPrefs } from "@/src/services/notificationActions";
import {
  DEFAULT_PREFS,
  getReminderPrefs,
  saveReminderPrefs,
  type ReminderPrefs,
} from "@/src/services/notificationPrefs";

function fmt12(t: string): string {
  const [h, m] = t.split(":").map((x) => parseInt(x, 10));
  const ampm = h >= 12 ? "PM" : "AM";
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return `${h12}:${String(m).padStart(2, "0")} ${ampm}`;
}

type PickerTarget = { type: "recap" } | { type: "hydration"; index: number | null };

type Cycle = { id: string; start_date: string; end_date?: string | null };

export default function Settings() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user, signOut, biometricEnabled, setBiometricEnabled } = useAuth();
  const [cycles, setCycles] = useState<Cycle[]>([]);
  const [prefs, setPrefs] = useState<ReminderPrefs>(DEFAULT_PREFS);
  const [pickerVisible, setPickerVisible] = useState(false);
  const [pickerTarget, setPickerTarget] = useState<PickerTarget | null>(null);
  const [pickerInitial, setPickerInitial] = useState("09:00");

  const load = useCallback(async () => {
    try {
      const c = await api.get<Cycle[]>("/cycles");
      setCycles(c);
    } catch {
      /* ignore */
    }
    setPrefs(await getReminderPrefs());
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  async function updatePrefs(next: ReminderPrefs, promptForPermission: boolean) {
    setPrefs(next);
    await saveReminderPrefs(next);
    if (Platform.OS === "web") return;
    const granted = await applyReminderPrefs({ prompt: promptForPermission, prefs: next });
    if (promptForPermission && !granted && (next.hydration || next.recap)) {
      Alert.alert(
        "Enable notifications",
        "Allow notifications for Cycle in your device settings to receive reminders.",
        [
          { text: "Not now", style: "cancel" },
          { text: "Open Settings", onPress: () => Linking.openSettings() },
        ],
      );
    }
  }

  function onToggleHydration(v: boolean) {
    updatePrefs({ ...prefs, hydration: v }, v);
  }
  function onToggleRecap(v: boolean) {
    updatePrefs({ ...prefs, recap: v }, v);
  }

  function openRecapPicker() {
    setPickerTarget({ type: "recap" });
    setPickerInitial(prefs.recapTime);
    setPickerVisible(true);
  }
  function openHydrationPicker(index: number | null) {
    setPickerTarget({ type: "hydration", index });
    setPickerInitial(index === null ? "12:00" : prefs.hydrationTimes[index]);
    setPickerVisible(true);
  }
  function removeHydrationTime(index: number) {
    const times = prefs.hydrationTimes.filter((_, i) => i !== index);
    updatePrefs({ ...prefs, hydrationTimes: times.length ? times : prefs.hydrationTimes }, false);
  }
  function onPickerConfirm(time: string) {
    if (pickerTarget?.type === "recap") {
      updatePrefs({ ...prefs, recapTime: time }, false);
    } else if (pickerTarget?.type === "hydration") {
      let times = [...prefs.hydrationTimes];
      if (pickerTarget.index === null) {
        if (!times.includes(time)) times.push(time);
      } else {
        times[pickerTarget.index] = time;
      }
      times = Array.from(new Set(times)).sort();
      updatePrefs({ ...prefs, hydrationTimes: times, hydration: true }, false);
    }
    setPickerVisible(false);
    setPickerTarget(null);
  }

  async function onToggleBiometric(v: boolean) {
    if (v && Platform.OS !== "web") {
      const has = await LocalAuthentication.hasHardwareAsync();
      const enrolled = await LocalAuthentication.isEnrolledAsync();
      if (!has || !enrolled) {
        Alert.alert(
          "Biometrics unavailable",
          "Set up Face ID or fingerprint on your device first. (Requires a development build, not Expo Go.)",
        );
        return;
      }
    }
    await setBiometricEnabled(v);
  }

  function deleteCycle(id: string) {
    Alert.alert("Delete this period?", "This cannot be undone.", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Delete",
        style: "destructive",
        onPress: async () => {
          await api.del(`/cycles/${id}`);
          load();
        },
      },
    ]);
  }

  async function handleLogout() {
    await signOut();
    router.replace("/(auth)/login");
  }

  return (
    <ScrollView
      testID="settings-screen"
      style={styles.screen}
      contentContainerStyle={{ paddingBottom: spacing.xxl, paddingTop: insets.top + spacing.sm }}
    >
      <View style={styles.header}>
        <Text style={styles.title}>Settings</Text>
        <TouchableOpacity testID="settings-close" onPress={() => router.back()} style={styles.closeBtn}>
          <Ionicons name="close" size={24} color={colors.text.secondary} />
        </TouchableOpacity>
      </View>

      <Card style={styles.card} testID="profile-card">
        <View style={styles.profileRow}>
          <View style={styles.avatar}>
            <Ionicons name="person" size={24} color={colors.brand.primary} />
          </View>
          <View>
            <Text style={styles.name}>{user?.full_name || "Cycle user"}</Text>
            <Text style={styles.email}>{user?.email}</Text>
          </View>
        </View>
      </Card>

      <Card style={styles.card} testID="security-card">
        <Text style={styles.sectionLabel}>Security</Text>
        <View style={styles.bioRow}>
          <View style={styles.bioLabel}>
            <Ionicons name="finger-print" size={20} color={colors.brand.primary} />
            <View style={{ marginLeft: spacing.sm, flex: 1 }}>
              <Text style={styles.bioTitle}>Biometric unlock</Text>
              <Text style={styles.bioSub}>Require Face ID / fingerprint to open the app</Text>
            </View>
          </View>
          <Switch
            testID="biometric-toggle"
            value={biometricEnabled}
            onValueChange={onToggleBiometric}
            trackColor={{ true: colors.brand.primary, false: colors.bg.tertiary }}
            thumbColor="#fff"
          />
        </View>
      </Card>

      <Card style={styles.card} testID="reminders-card">
        <Text style={styles.sectionLabel}>Reminders</Text>

        <View style={styles.bioRow}>
          <View style={styles.bioLabel}>
            <Ionicons name="water-outline" size={20} color="#2E9BD6" />
            <View style={{ marginLeft: spacing.sm, flex: 1 }}>
              <Text style={styles.bioTitle}>Hydration reminders</Text>
              <Text style={styles.bioSub}>Choose any times you like</Text>
            </View>
          </View>
          <Switch
            testID="hydration-reminder-toggle"
            value={prefs.hydration}
            onValueChange={onToggleHydration}
            trackColor={{ true: colors.brand.primary, false: colors.bg.tertiary }}
            thumbColor="#fff"
          />
        </View>

        {prefs.hydration && (
          <View style={styles.timeRow} testID="hydration-times-row">
            {prefs.hydrationTimes.map((t, i) => (
              <View key={`${t}-${i}`} style={styles.editChip} testID={`hydration-time-${t}`}>
                <TouchableOpacity
                  testID={`hydration-edit-${i}`}
                  onPress={() => openHydrationPicker(i)}
                  hitSlop={6}
                >
                  <Text style={styles.editChipText}>{fmt12(t)}</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  testID={`hydration-remove-${i}`}
                  onPress={() => removeHydrationTime(i)}
                  hitSlop={8}
                  style={styles.chipX}
                >
                  <Ionicons name="close" size={13} color={colors.text.tertiary} />
                </TouchableOpacity>
              </View>
            ))}
            <TouchableOpacity
              testID="hydration-add-time"
              style={styles.addChip}
              onPress={() => openHydrationPicker(null)}
            >
              <Ionicons name="add" size={14} color={colors.brand.primary} />
              <Text style={styles.addChipText}>Add time</Text>
            </TouchableOpacity>
          </View>
        )}

        <View style={[styles.bioRow, styles.rowDivider]}>
          <View style={styles.bioLabel}>
            <Ionicons name="sparkles-outline" size={20} color={colors.brand.primary} />
            <View style={{ marginLeft: spacing.sm, flex: 1 }}>
              <Text style={styles.bioTitle}>Daily recap</Text>
              <Text style={styles.bioSub}>An evening summary of your day</Text>
            </View>
          </View>
          <Switch
            testID="recap-reminder-toggle"
            value={prefs.recap}
            onValueChange={onToggleRecap}
            trackColor={{ true: colors.brand.primary, false: colors.bg.tertiary }}
            thumbColor="#fff"
          />
        </View>

        {prefs.recap && (
          <TouchableOpacity
            testID="recap-time-button"
            style={styles.timeSetRow}
            onPress={openRecapPicker}
            activeOpacity={0.7}
          >
            <Text style={styles.timeSetLabel}>Reminder time</Text>
            <View style={styles.timeSetValue}>
              <Ionicons name="time-outline" size={16} color={colors.brand.primary} />
              <Text style={styles.timeSetValueText} testID="recap-time-value">{fmt12(prefs.recapTime)}</Text>
              <Ionicons name="chevron-forward" size={16} color={colors.text.tertiary} />
            </View>
          </TouchableOpacity>
        )}

        {Platform.OS !== "web" && (
          <Text style={styles.reminderNote}>
            Reminders &amp; lock-screen actions fire on a development/production build, not in Expo Go.
          </Text>
        )}
      </Card>

      <Card style={styles.card} testID="data-privacy-card">
        <Text style={styles.sectionLabel}>Data & Privacy</Text>

        <TouchableOpacity
          testID="nav-backup"
          style={styles.navRow}
          onPress={() => router.push("/backup")}
          activeOpacity={0.7}
        >
          <Ionicons name="shield-checkmark-outline" size={20} color={colors.brand.primary} />
          <View style={styles.navTextWrap}>
            <Text style={styles.navTitle}>Backup & Restore</Text>
            <Text style={styles.navSub}>Snapshot your data and restore any time</Text>
          </View>
          <Ionicons name="chevron-forward" size={18} color={colors.text.tertiary} />
        </TouchableOpacity>

        <TouchableOpacity
          testID="nav-activity-log"
          style={[styles.navRow, styles.rowDivider]}
          onPress={() => router.push("/activity-log")}
          activeOpacity={0.7}
        >
          <Ionicons name="time-outline" size={20} color={colors.brand.primary} />
          <View style={styles.navTextWrap}>
            <Text style={styles.navTitle}>Activity log</Text>
            <Text style={styles.navSub}>A private history of changes to your data</Text>
          </View>
          <Ionicons name="chevron-forward" size={18} color={colors.text.tertiary} />
        </TouchableOpacity>

        <TouchableOpacity
          testID="nav-offline-diagnostics"
          style={[styles.navRow, styles.rowDivider]}
          onPress={() => router.push("/offline-diagnostics")}
          activeOpacity={0.7}
        >
          <Ionicons name="cloud-offline-outline" size={20} color={colors.brand.primary} />
          <View style={styles.navTextWrap}>
            <Text style={styles.navTitle}>Offline & sync</Text>
            <Text style={styles.navSub}>Check pending writes and test offline sync</Text>
          </View>
          <Ionicons name="chevron-forward" size={18} color={colors.text.tertiary} />
        </TouchableOpacity>
      </Card>

      <Card style={styles.card} testID="cycle-history-card">
        <Text style={styles.sectionLabel}>Period history</Text>
        {cycles.length ? (
          cycles.map((c) => (
            <View key={c.id} style={styles.cycleRow} testID={`cycle-row-${c.id}`}>
              <View>
                <Text style={styles.cycleDate}>
                  {formatNice(c.start_date)}
                  {c.end_date ? ` – ${formatNice(c.end_date)}` : " (ongoing)"}
                </Text>
              </View>
              <TouchableOpacity testID={`delete-cycle-${c.id}`} onPress={() => deleteCycle(c.id)}>
                <Ionicons name="trash-outline" size={18} color={colors.status.error} />
              </TouchableOpacity>
            </View>
          ))
        ) : (
          <Text style={styles.empty}>No periods logged yet.</Text>
        )}
      </Card>

      <View style={{ paddingHorizontal: spacing.screen, marginTop: spacing.lg }}>
        <PrimaryButton
          testID="logout-button"
          title="Sign out"
          variant="secondary"
          icon="log-out-outline"
          onPress={handleLogout}
        />
      </View>

      <Text style={styles.footer}>Cycle • Privacy-first menstrual health</Text>

      <TimePickerModal
        visible={pickerVisible}
        initial={pickerInitial}
        title={pickerTarget?.type === "recap" ? "Daily recap time" : "Hydration reminder time"}
        onCancel={() => {
          setPickerVisible(false);
          setPickerTarget(null);
        }}
        onConfirm={onPickerConfirm}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg.primary },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.screen,
    marginBottom: spacing.md,
  },
  title: { ...type.h1, color: colors.text.primary },
  closeBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.bg.secondary, alignItems: "center", justifyContent: "center" },
  card: { marginHorizontal: spacing.screen, marginTop: spacing.md },
  profileRow: { flexDirection: "row", alignItems: "center" },
  avatar: { width: 52, height: 52, borderRadius: 26, backgroundColor: colors.brand.primaryLight, alignItems: "center", justifyContent: "center", marginRight: spacing.md },
  name: { ...type.h3, color: colors.text.primary },
  email: { ...type.bodySm, color: colors.text.tertiary },
  sectionLabel: { ...type.caption, color: colors.text.tertiary, marginBottom: spacing.md },
  bioRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  bioLabel: { flexDirection: "row", alignItems: "center", flex: 1, marginRight: spacing.md },
  bioTitle: { ...type.body, color: colors.text.primary, fontWeight: "600" },
  bioSub: { ...type.bodySm, color: colors.text.tertiary },
  rowDivider: { borderTopWidth: 1, borderTopColor: colors.ui.divider, marginTop: spacing.md, paddingTop: spacing.md },
  timeRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs, marginTop: spacing.md },
  timeChip: {
    paddingVertical: 6,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    backgroundColor: colors.bg.secondary,
    borderWidth: 1,
    borderColor: colors.ui.border,
  },
  timeChipActive: { backgroundColor: colors.brand.primary, borderColor: colors.brand.primary },
  timeChipText: { ...type.bodySm, color: colors.text.secondary, fontWeight: "600" },
  timeChipTextActive: { color: "#fff" },
  reminderNote: { ...type.bodySm, color: colors.text.tertiary, marginTop: spacing.md },
  editChip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingVertical: 6,
    paddingLeft: spacing.md,
    paddingRight: spacing.sm,
    borderRadius: radius.pill,
    backgroundColor: "#2E9BD6" + "15",
    borderWidth: 1,
    borderColor: "#2E9BD6" + "33",
  },
  editChipText: { ...type.bodySm, color: "#1E6FA0", fontWeight: "700" },
  chipX: { width: 18, height: 18, borderRadius: 9, alignItems: "center", justifyContent: "center", backgroundColor: colors.bg.primary },
  addChip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 3,
    paddingVertical: 6,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.brand.primary,
    borderStyle: "dashed",
  },
  addChipText: { ...type.bodySm, color: colors.brand.primary, fontWeight: "700" },
  timeSetRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: spacing.md,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    backgroundColor: colors.bg.secondary,
    borderRadius: radius.md,
  },
  timeSetLabel: { ...type.body, color: colors.text.secondary },
  timeSetValue: { flexDirection: "row", alignItems: "center", gap: 4 },
  timeSetValueText: { ...type.body, color: colors.text.primary, fontWeight: "700" },
  navRow: { flexDirection: "row", alignItems: "center", paddingVertical: spacing.sm },
  navTextWrap: { flex: 1, marginLeft: spacing.sm },
  navTitle: { ...type.body, color: colors.text.primary, fontWeight: "600" },
  navSub: { ...type.bodySm, color: colors.text.tertiary, marginTop: 1 },
  cycleRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.ui.divider },
  cycleDate: { ...type.body, color: colors.text.primary },
  empty: { ...type.body, color: colors.text.tertiary },
  footer: { ...type.bodySm, color: colors.text.tertiary, textAlign: "center", marginTop: spacing.xl },
});
