import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import {
  Alert,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import {
  KeyboardAwareScrollView,
  KeyboardStickyView,
} from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api/client";
import { Chip, PrimaryButton } from "@/src/components/ui";
import { MOODS, SEVERITIES, Severity, SYMPTOMS } from "@/src/constants";
import { colors, radius, spacing, type } from "@/src/theme";
import { formatLong, todayISO } from "@/src/utils/cycle";

type SymptomState = Record<string, Severity>;

export default function LogScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const params = useLocalSearchParams<{ date?: string; focus?: string }>();
  const date = params.date || todayISO();

  const [symptoms, setSymptoms] = useState<SymptomState>({});
  const [moods, setMoods] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const [tags, setTags] = useState("");
  const [shared, setShared] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const log = await api.get(`/logs/${date}`);
        const sym: SymptomState = {};
        (log.symptoms || []).forEach((s: any) => (sym[s.name] = s.severity));
        setSymptoms(sym);
        setMoods(log.moods || []);
        setNote(log.note || "");
        setTags((log.tags || []).join(", "));
        setShared(log.visibility === "shared");
      } catch {
        /* ignore */
      } finally {
        setLoading(false);
      }
    })();
  }, [date]);

  function toggleSymptom(name: string) {
    setSymptoms((prev) => {
      const next = { ...prev };
      if (next[name]) delete next[name];
      else next[name] = "mild";
      return next;
    });
  }

  function setSeverity(name: string, sev: Severity) {
    setSymptoms((prev) => ({ ...prev, [name]: sev }));
  }

  function toggleMood(name: string) {
    setMoods((prev) => (prev.includes(name) ? prev.filter((m) => m !== name) : [...prev, name]));
  }

  async function save() {
    setSaving(true);
    try {
      await api.post("/logs", {
        date,
        symptoms: Object.entries(symptoms).map(([name, severity]) => ({ name, severity })),
        moods,
        note,
        tags: tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        visibility: shared ? "shared" : "private",
      });
      router.back();
    } catch (e: any) {
      Alert.alert(
        "Couldn't save log",
        e?.message || "Please check your connection and try again.",
      );
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <View style={styles.screen} testID="log-loading" />;

  return (
    <View style={styles.screen} testID="log-screen">
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <View>
          <Text style={styles.headerTitle}>Daily log</Text>
          <Text style={styles.headerDate}>{formatLong(date)}</Text>
        </View>
        <TouchableOpacity testID="log-close-button" onPress={() => router.back()} style={styles.closeBtn}>
          <Ionicons name="close" size={24} color={colors.text.secondary} />
        </TouchableOpacity>
      </View>

      <KeyboardAwareScrollView
        bottomOffset={90}
        contentContainerStyle={{ padding: spacing.screen, paddingBottom: 120 }}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={styles.section}>Symptoms</Text>
        {SYMPTOMS.map((s) => {
          const active = !!symptoms[s.name];
          return (
            <View key={s.name} style={styles.symptomBlock}>
              <TouchableOpacity
                testID={`symptom-${s.name}`}
                style={styles.symptomRow}
                activeOpacity={0.7}
                onPress={() => toggleSymptom(s.name)}
              >
                <View style={styles.symptomLabel}>
                  <Ionicons
                    name={s.icon as any}
                    size={18}
                    color={active ? colors.brand.primary : colors.text.tertiary}
                  />
                  <Text style={[styles.symptomName, active && styles.symptomNameActive]}>
                    {s.name}
                  </Text>
                </View>
                <Ionicons
                  name={active ? "checkmark-circle" : "ellipse-outline"}
                  size={22}
                  color={active ? colors.brand.primary : colors.text.tertiary}
                />
              </TouchableOpacity>
              {active && (
                <View style={styles.severityRow}>
                  {SEVERITIES.map((sev) => (
                    <TouchableOpacity
                      key={sev}
                      testID={`severity-${s.name}-${sev}`}
                      style={[
                        styles.sevBtn,
                        symptoms[s.name] === sev && styles.sevBtnActive,
                      ]}
                      onPress={() => setSeverity(s.name, sev)}
                    >
                      <Text
                        style={[
                          styles.sevText,
                          symptoms[s.name] === sev && styles.sevTextActive,
                        ]}
                      >
                        {sev}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
              )}
            </View>
          );
        })}

        <Text style={[styles.section, { marginTop: spacing.xl }]}>Mood</Text>
        <View style={styles.chipWrap}>
          {MOODS.map((m) => (
            <Chip
              key={m.name}
              testID={`mood-${m.name}`}
              label={m.name}
              selected={moods.includes(m.name)}
              onPress={() => toggleMood(m.name)}
            />
          ))}
        </View>

        <Text style={[styles.section, { marginTop: spacing.xl }]}>Journal</Text>
        <TextInput
          testID="log-note-input"
          value={note}
          onChangeText={setNote}
          placeholder="How are you feeling today?"
          placeholderTextColor={colors.text.tertiary}
          multiline
          style={styles.noteInput}
        />
        <TextInput
          testID="log-tags-input"
          value={tags}
          onChangeText={setTags}
          placeholder="Tags (comma separated)"
          placeholderTextColor={colors.text.tertiary}
          style={styles.tagsInput}
        />

        <TouchableOpacity
          testID="log-visibility-toggle"
          style={styles.visRow}
          activeOpacity={0.7}
          onPress={() => setShared((v) => !v)}
        >
          <View style={styles.visLabel}>
            <Ionicons
              name={shared ? "people-outline" : "lock-closed-outline"}
              size={18}
              color={shared ? colors.brand.primary : colors.text.secondary}
            />
            <View style={{ marginLeft: spacing.sm }}>
              <Text style={styles.visTitle}>{shared ? "Shared with partner" : "Private"}</Text>
              <Text style={styles.visSub}>
                {shared ? "Visible in partner's read-only view" : "Only you can see this"}
              </Text>
            </View>
          </View>
          <View style={[styles.toggle, shared && styles.toggleOn]}>
            <View style={[styles.knob, shared && styles.knobOn]} />
          </View>
        </TouchableOpacity>
      </KeyboardAwareScrollView>

      <KeyboardStickyView offset={{ closed: 0, opened: insets.bottom }}>
        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.sm }]}>
          <PrimaryButton testID="log-save-button" title="Save log" onPress={save} loading={saving} />
        </View>
      </KeyboardStickyView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg.primary },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.screen,
    paddingBottom: spacing.md,
  },
  headerTitle: { ...type.h2, color: colors.text.primary },
  headerDate: { ...type.bodySm, color: colors.text.tertiary },
  closeBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.bg.secondary,
    alignItems: "center",
    justifyContent: "center",
  },
  section: { ...type.caption, color: colors.text.tertiary, marginBottom: spacing.md },
  symptomBlock: { marginBottom: spacing.sm },
  symptomRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: spacing.sm },
  symptomLabel: { flexDirection: "row", alignItems: "center" },
  symptomName: { ...type.body, color: colors.text.secondary, marginLeft: spacing.sm },
  symptomNameActive: { color: colors.text.primary, fontWeight: "600" },
  severityRow: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.sm },
  sevBtn: {
    flex: 1,
    paddingVertical: 8,
    borderRadius: radius.sm,
    backgroundColor: colors.bg.secondary,
    alignItems: "center",
  },
  sevBtnActive: { backgroundColor: colors.brand.primary },
  sevText: { ...type.bodySm, color: colors.text.secondary, textTransform: "capitalize" },
  sevTextActive: { color: "#fff", fontWeight: "600" },
  chipWrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  noteInput: {
    backgroundColor: colors.bg.secondary,
    borderRadius: radius.md,
    padding: spacing.md,
    minHeight: 100,
    textAlignVertical: "top",
    fontSize: 16,
    color: colors.text.primary,
  },
  tagsInput: {
    backgroundColor: colors.bg.secondary,
    borderRadius: radius.md,
    padding: spacing.md,
    marginTop: spacing.sm,
    fontSize: 15,
    color: colors.text.primary,
  },
  visRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: spacing.lg,
    padding: spacing.md,
    backgroundColor: colors.bg.secondary,
    borderRadius: radius.md,
  },
  visLabel: { flexDirection: "row", alignItems: "center", flex: 1 },
  visTitle: { ...type.body, color: colors.text.primary, fontWeight: "600" },
  visSub: { ...type.bodySm, color: colors.text.tertiary },
  toggle: { width: 48, height: 28, borderRadius: 14, backgroundColor: colors.bg.tertiary, padding: 3, justifyContent: "center" },
  toggleOn: { backgroundColor: colors.brand.primary },
  knob: { width: 22, height: 22, borderRadius: 11, backgroundColor: "#fff" },
  knobOn: { alignSelf: "flex-end" },
  footer: {
    paddingHorizontal: spacing.screen,
    paddingTop: spacing.sm,
    backgroundColor: colors.bg.primary,
    borderTopWidth: 1,
    borderTopColor: colors.ui.divider,
  },
});
