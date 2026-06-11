import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect } from "expo-router";

import { api } from "@/src/api/client";
import { Card } from "@/src/components/ui";
import { colors, radius, spacing, type } from "@/src/theme";

type Note = { id: string; author_name: string; text: string; created_at: string; mine: boolean };
type Checkin = {
  id: string;
  from_name: string;
  prompt: string;
  response: string | null;
  created_at: string;
  mine: boolean;
  can_respond: boolean;
};
type Todo = { id: string; text: string; done: boolean; created_by_name: string };
type Support = { id: string; label: string; actor_name: string; created_at: string; mine: boolean };

const PROMPTS = ["How are you feeling?", "Need anything?", "Thinking of you ♥"];
const RESPONSES = ["Good", "Okay", "Need support", "Resting"];

function timeShort(iso?: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) +
    " · " + d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

export default function PartnerSpace() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const params = useLocalSearchParams<{ id?: string; name?: string }>();
  const linkId = params.id || "";

  const [loading, setLoading] = useState(true);
  const [notes, setNotes] = useState<Note[]>([]);
  const [checkins, setCheckins] = useState<Checkin[]>([]);
  const [todos, setTodos] = useState<Todo[]>([]);
  const [support, setSupport] = useState<Support[]>([]);
  const [noteText, setNoteText] = useState("");
  const [todoText, setTodoText] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [n, c, t, s] = await Promise.all([
        api.get<{ notes: Note[] }>(`/partner/${linkId}/notes`),
        api.get<{ checkins: Checkin[] }>(`/partner/${linkId}/checkins`),
        api.get<{ todos: Todo[] }>(`/partner/${linkId}/todos`),
        api.get<{ support: Support[] }>(`/partner/${linkId}/support`),
      ]);
      setNotes(n.notes);
      setCheckins(c.checkins);
      setTodos(t.todos);
      setSupport(s.support);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [linkId]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  async function sendCheckin(prompt: string) {
    setBusy(true);
    try {
      const c = await api.post<Checkin>(`/partner/${linkId}/checkins`, { prompt });
      setCheckins((prev) => [c, ...prev]);
    } finally {
      setBusy(false);
    }
  }

  async function respondCheckin(id: string, response: string) {
    const c = await api.post<Checkin>(`/partner/${linkId}/checkins/${id}/respond`, { response });
    setCheckins((prev) => prev.map((x) => (x.id === id ? c : x)));
  }

  async function addTodo() {
    const text = todoText.trim();
    if (!text) return;
    setTodoText("");
    const t = await api.post<Todo>(`/partner/${linkId}/todos`, { text });
    setTodos((prev) => [t, ...prev.filter((x) => !x.done)].concat(prev.filter((x) => x.done)));
  }

  async function toggleTodo(item: Todo) {
    setTodos((prev) => prev.map((x) => (x.id === item.id ? { ...x, done: !x.done } : x)));
    try {
      await api.put(`/partner/${linkId}/todos/${item.id}`, { done: !item.done });
    } catch {
      load();
    }
  }

  async function deleteTodo(id: string) {
    setTodos((prev) => prev.filter((x) => x.id !== id));
    try {
      await api.del(`/partner/${linkId}/todos/${id}`);
    } catch {
      load();
    }
  }

  async function addNote() {
    const text = noteText.trim();
    if (!text) return;
    setNoteText("");
    const n = await api.post<Note>(`/partner/${linkId}/notes`, { text });
    setNotes((prev) => [{ ...n, mine: true }, ...prev]);
  }

  function confirmDeleteNote(id: string) {
    const doIt = async () => {
      setNotes((prev) => prev.filter((x) => x.id !== id));
      try {
        await api.del(`/partner/${linkId}/notes/${id}`);
      } catch {
        load();
      }
    };
    if (Platform.OS === "web") {
      if (window.confirm("Delete this note?")) doIt();
    } else {
      Alert.alert("Delete note?", "", [
        { text: "Cancel", style: "cancel" },
        { text: "Delete", style: "destructive", onPress: doIt },
      ]);
    }
  }

  return (
    <View style={styles.screen} testID="partner-space-screen">
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <TouchableOpacity testID="ps-back" onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.text.primary} />
        </TouchableOpacity>
        <View>
          <Text style={styles.headerTitle}>Shared space</Text>
          <Text style={styles.headerSub}>
            {params.name ? `With ${params.name}` : "A private space, just for you two"}
          </Text>
        </View>
      </View>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={colors.brand.primary} />
        </View>
      ) : (
        <KeyboardAwareScrollView
          bottomOffset={24}
          contentContainerStyle={{ padding: spacing.screen, paddingBottom: spacing.xxl }}
        >
          {/* ---- Check-ins ---- */}
          <Card style={styles.card} testID="ps-checkins">
            <Text style={styles.sectionLabel}>Check in</Text>
            <View style={styles.chipRow}>
              {PROMPTS.map((p, i) => (
                <TouchableOpacity
                  key={p}
                  testID={`ps-checkin-prompt-${i}`}
                  style={styles.promptChip}
                  disabled={busy}
                  onPress={() => sendCheckin(p)}
                >
                  <Text style={styles.promptChipText}>{p}</Text>
                </TouchableOpacity>
              ))}
            </View>
            {checkins.length === 0 ? (
              <Text style={styles.empty}>No check-ins yet. Send one above.</Text>
            ) : (
              checkins.map((c) => (
                <View key={c.id} style={styles.checkinRow} testID={`ps-checkin-${c.id}`}>
                  <View style={styles.checkinHead}>
                    <Ionicons name="chatbubble-ellipses-outline" size={15} color={colors.brand.primary} />
                    <Text style={styles.checkinPrompt}>{c.prompt}</Text>
                  </View>
                  <Text style={styles.checkinMeta}>
                    {c.mine ? "You" : c.from_name} · {timeShort(c.created_at)}
                  </Text>
                  {c.response ? (
                    <View style={styles.responseBubble}>
                      <Ionicons name="checkmark-circle" size={14} color={colors.status.success} />
                      <Text style={styles.responseText}>{c.response}</Text>
                    </View>
                  ) : c.can_respond ? (
                    <View style={styles.respRow}>
                      {RESPONSES.map((r) => (
                        <TouchableOpacity
                          key={r}
                          testID={`ps-respond-${c.id}-${r}`}
                          style={styles.respChip}
                          onPress={() => respondCheckin(c.id, r)}
                        >
                          <Text style={styles.respChipText}>{r}</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  ) : (
                    <Text style={styles.awaiting}>Waiting for a reply…</Text>
                  )}
                </View>
              ))
            )}
          </Card>

          {/* ---- Shared to-do ---- */}
          <Card style={styles.card} testID="ps-todos">
            <Text style={styles.sectionLabel}>Shared to-do</Text>
            <View style={styles.inputRow}>
              <TextInput
                testID="ps-todo-input"
                value={todoText}
                onChangeText={setTodoText}
                placeholder="Buy medication, heating pad…"
                placeholderTextColor={colors.text.tertiary}
                style={styles.input}
                returnKeyType="done"
                onSubmitEditing={addTodo}
              />
              <TouchableOpacity testID="ps-todo-add" style={styles.addBtn} onPress={addTodo}>
                <Ionicons name="add" size={22} color="#fff" />
              </TouchableOpacity>
            </View>
            {todos.length === 0 ? (
              <Text style={styles.empty}>No items yet.</Text>
            ) : (
              todos.map((t) => (
                <View key={t.id} style={styles.todoRow} testID={`ps-todo-${t.id}`}>
                  <TouchableOpacity
                    testID={`ps-todo-toggle-${t.id}`}
                    onPress={() => toggleTodo(t)}
                    style={styles.todoCheck}
                  >
                    <Ionicons
                      name={t.done ? "checkbox" : "square-outline"}
                      size={22}
                      color={t.done ? colors.brand.primary : colors.text.tertiary}
                    />
                  </TouchableOpacity>
                  <Text style={[styles.todoText, t.done && styles.todoDone]}>{t.text}</Text>
                  <TouchableOpacity testID={`ps-todo-del-${t.id}`} onPress={() => deleteTodo(t.id)}>
                    <Ionicons name="close" size={18} color={colors.text.tertiary} />
                  </TouchableOpacity>
                </View>
              ))
            )}
          </Card>

          {/* ---- Partner notes ---- */}
          <Card style={styles.card} testID="ps-notes">
            <Text style={styles.sectionLabel}>Supportive notes</Text>
            <Text style={styles.helpText}>Leave a kind word. Kept separate from medical notes.</Text>
            <View style={styles.inputRow}>
              <TextInput
                testID="ps-note-input"
                value={noteText}
                onChangeText={setNoteText}
                placeholder="Remember to rest…"
                placeholderTextColor={colors.text.tertiary}
                style={[styles.input, { minHeight: 44 }]}
                multiline
              />
              <TouchableOpacity testID="ps-note-send" style={styles.addBtn} onPress={addNote}>
                <Ionicons name="send" size={18} color="#fff" />
              </TouchableOpacity>
            </View>
            {notes.length === 0 ? (
              <Text style={styles.empty}>No notes yet.</Text>
            ) : (
              notes.map((n) => (
                <View
                  key={n.id}
                  style={[styles.noteBubble, n.mine && styles.noteMine]}
                  testID={`ps-note-${n.id}`}
                >
                  <View style={styles.noteHead}>
                    <Text style={styles.noteAuthor}>{n.mine ? "You" : n.author_name}</Text>
                    <Text style={styles.noteTime}>{timeShort(n.created_at)}</Text>
                  </View>
                  <Text style={styles.noteText}>{n.text}</Text>
                  {n.mine ? (
                    <TouchableOpacity
                      testID={`ps-note-del-${n.id}`}
                      style={styles.noteDel}
                      onPress={() => confirmDeleteNote(n.id)}
                    >
                      <Ionicons name="trash-outline" size={15} color={colors.text.tertiary} />
                    </TouchableOpacity>
                  ) : null}
                </View>
              ))
            )}
          </Card>

          {/* ---- Support history ---- */}
          <Card style={styles.card} testID="ps-support">
            <Text style={styles.sectionLabel}>Support history</Text>
            <Text style={styles.helpText}>A record of caring actions — never surveillance.</Text>
            {support.length === 0 ? (
              <Text style={styles.empty}>Supportive actions will appear here.</Text>
            ) : (
              support.slice(0, 20).map((s) => (
                <View key={s.id} style={styles.supportRow} testID={`ps-support-${s.id}`}>
                  <Ionicons name="heart-circle" size={18} color={colors.brand.primary} />
                  <Text style={styles.supportText}>{s.label}</Text>
                  <Text style={styles.supportTime}>{s.mine ? "You" : s.actor_name}</Text>
                </View>
              ))
            )}
          </Card>
        </KeyboardAwareScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg.primary },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingBottom: spacing.md },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center", marginRight: spacing.xs },
  headerTitle: { ...type.h2, color: colors.text.primary },
  headerSub: { ...type.bodySm, color: colors.text.secondary, marginTop: 2 },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  card: { marginBottom: spacing.md },
  sectionLabel: { ...type.caption, color: colors.text.tertiary, marginBottom: spacing.sm },
  helpText: { ...type.bodySm, color: colors.text.secondary, marginBottom: spacing.sm },
  empty: { ...type.bodySm, color: colors.text.tertiary, marginTop: spacing.xs },

  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginBottom: spacing.sm },
  promptChip: {
    backgroundColor: colors.brand.primaryLight,
    paddingVertical: 8,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
  },
  promptChipText: { ...type.bodySm, color: colors.brand.primary, fontWeight: "600" },

  checkinRow: { paddingVertical: spacing.sm, borderTopWidth: 1, borderTopColor: colors.ui.divider },
  checkinHead: { flexDirection: "row", alignItems: "center" },
  checkinPrompt: { ...type.body, color: colors.text.primary, fontWeight: "600", marginLeft: 6, flex: 1 },
  checkinMeta: { ...type.bodySm, color: colors.text.tertiary, marginTop: 2, marginLeft: 21 },
  respRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs, marginTop: spacing.sm, marginLeft: 21 },
  respChip: {
    backgroundColor: colors.bg.secondary,
    paddingVertical: 6,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.ui.border,
  },
  respChipText: { ...type.bodySm, color: colors.text.primary, fontWeight: "600" },
  responseBubble: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "flex-start",
    backgroundColor: "#EAF5EF",
    paddingVertical: 5,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    marginTop: spacing.sm,
    marginLeft: 21,
  },
  responseText: { ...type.bodySm, color: colors.status.success, fontWeight: "700", marginLeft: 5 },
  awaiting: { ...type.bodySm, color: colors.text.tertiary, fontStyle: "italic", marginTop: 6, marginLeft: 21 },

  inputRow: { flexDirection: "row", alignItems: "flex-end", gap: spacing.sm, marginBottom: spacing.sm },
  input: {
    flex: 1,
    backgroundColor: colors.bg.secondary,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 12,
    fontSize: 15,
    color: colors.text.primary,
  },
  addBtn: {
    width: 44,
    height: 44,
    borderRadius: radius.md,
    backgroundColor: colors.brand.primary,
    alignItems: "center",
    justifyContent: "center",
  },

  todoRow: { flexDirection: "row", alignItems: "center", paddingVertical: spacing.sm },
  todoCheck: { marginRight: spacing.sm },
  todoText: { ...type.body, color: colors.text.primary, flex: 1 },
  todoDone: { textDecorationLine: "line-through", color: colors.text.tertiary },

  noteBubble: {
    backgroundColor: colors.bg.secondary,
    borderRadius: radius.md,
    padding: spacing.md,
    marginTop: spacing.sm,
  },
  noteMine: { backgroundColor: colors.brand.primaryLight },
  noteHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 4 },
  noteAuthor: { ...type.bodySm, color: colors.brand.primary, fontWeight: "700" },
  noteTime: { ...type.bodySm, color: colors.text.tertiary },
  noteText: { ...type.body, color: colors.text.primary },
  noteDel: { alignSelf: "flex-end", marginTop: 4 },
  supportRow: { flexDirection: "row", alignItems: "center", paddingVertical: spacing.sm },
  supportText: { ...type.body, color: colors.text.primary, flex: 1, marginLeft: spacing.sm },
  supportTime: { ...type.bodySm, color: colors.text.tertiary },
});
