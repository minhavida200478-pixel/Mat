import { Ionicons } from "@expo/vector-icons";
import { Image } from "expo-image";
import * as Clipboard from "expo-clipboard";
import { useRouter } from "expo-router";
import { useState } from "react";
import {
  Alert,
  Platform,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api/client";
import { Card, PrimaryButton } from "@/src/components/ui";
import { useFetch } from "@/src/hooks/useFetch";
import { colors, radius, spacing, type } from "@/src/theme";
import { media } from "@/src/theme";

type Flags = {
  periods: boolean;
  fertility: boolean;
  symptoms: boolean;
  moods: boolean;
  notes: boolean;
  hydration: boolean;
  meals: boolean;
  medications: boolean;
  activity: boolean;
  timeline: boolean;
  digest: boolean;
};
type SharingLink = {
  id: string;
  token: string;
  status: string;
  partner_name: string | null;
  sharing_flags: Flags;
  emergency_contact?: boolean;
  expires_at: string;
};
type ViewingLink = { id: string; owner_name: string };

const ALL_FLAGS: Flags = {
  periods: false,
  fertility: false,
  symptoms: false,
  moods: false,
  notes: false,
  hydration: false,
  meals: false,
  medications: false,
  activity: false,
  timeline: false,
  digest: false,
};

const FLAG_META: { key: keyof Flags; label: string; icon: string }[] = [
  { key: "periods", label: "Cycle & periods", icon: "water-outline" },
  { key: "fertility", label: "Fertility window", icon: "leaf-outline" },
  { key: "symptoms", label: "Symptoms", icon: "pulse-outline" },
  { key: "moods", label: "Moods", icon: "happy-outline" },
  { key: "notes", label: "Journal notes", icon: "document-text-outline" },
  { key: "hydration", label: "Hydration", icon: "water" },
  { key: "meals", label: "Meals", icon: "restaurant-outline" },
  { key: "medications", label: "Medications", icon: "medkit-outline" },
  { key: "activity", label: "Intimacy", icon: "heart-outline" },
  { key: "timeline", label: "Activity timeline", icon: "time-outline" },
  { key: "digest", label: "Weekly digest", icon: "newspaper-outline" },
];

export default function Partner() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);

  const { data, refetch: load, setData } = useFetch<{ sharing: SharingLink[]; viewing: ViewingLink[] }>(
    () => api.get("/partner/links"),
    { refetchOnFocus: true },
  );
  const sharing = data?.sharing ?? [];
  const viewing = data?.viewing ?? [];

  async function generateInvite() {
    setBusy(true);
    try {
      await api.post("/partner/invite");
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function acceptCode() {
    if (!code.trim()) return;
    setBusy(true);
    try {
      const r = await api.post("/partner/accept", { token: code.trim().toUpperCase() });
      setCode("");
      await load();
      Alert.alert("Linked!", `You can now view ${r.owner_name}'s shared data.`);
    } catch (e: any) {
      Alert.alert("Could not link", e?.message || "Invalid code.");
    } finally {
      setBusy(false);
    }
  }

  async function toggleFlag(link: SharingLink, key: keyof Flags) {
    // Always send a complete flag set so the backend never falls back to defaults
    // for categories the user hasn't explicitly enabled.
    const next: Flags = { ...ALL_FLAGS, ...link.sharing_flags, [key]: !link.sharing_flags[key] };
    setData((prev) =>
      prev
        ? { ...prev, sharing: prev.sharing.map((l) => (l.id === link.id ? { ...l, sharing_flags: next } : l)) }
        : prev,
    );
    try {
      await api.put(`/partner/links/${link.id}/permissions`, next);
    } catch {
      load();
    }
  }

  async function setEmergency(link: SharingLink, enabled: boolean) {
    setData((prev) =>
      prev
        ? { ...prev, sharing: prev.sharing.map((l) => (l.id === link.id ? { ...l, emergency_contact: enabled } : l)) }
        : prev,
    );
    try {
      await api.put(`/partner/links/${link.id}/emergency`, { enabled });
    } catch {
      load();
    }
  }

  async function sendAlert(link: SharingLink) {
    const submit = async (message: string) => {
      const msg = (message || "").trim();
      if (!msg) return;
      try {
        await api.post(`/partner/${link.id}/alerts`, { message: msg });
        Alert.alert("Alert sent", `${link.partner_name || "Your partner"} will see it on their dashboard.`);
      } catch (e: any) {
        Alert.alert("Could not send", e?.message || "Try again.");
      }
    };
    if (Platform.OS === "ios") {
      Alert.prompt("Send health alert", "This goes to your emergency contact.", submit);
    } else if (Platform.OS === "web") {
      const m = window.prompt("Send a health alert to your emergency contact:");
      if (m) submit(m);
    } else {
      submit("I need support right now, please reach out.");
    }
  }

  async function copyToken(token: string) {
    await Clipboard.setStringAsync(token);
    if (Platform.OS === "web") {
      window.alert("Invite code copied to clipboard.");
    } else {
      Alert.alert("Copied", "Invite code copied to clipboard.");
    }
  }

  async function revoke(id: string) {
    const doRevoke = async () => {
      try {
        await api.del(`/partner/links/${id}`);
        load();
      } catch (e: any) {
        const errorMsg = e?.message || "Failed to remove partner link.";
        if (Platform.OS === "web") {
          window.alert(errorMsg);
        } else {
          Alert.alert("Error", errorMsg);
        }
      }
    };

    if (Platform.OS === "web") {
      const confirmed = window.confirm("Remove partner link?\n\nThis stops all data sharing for this link.");
      if (confirmed) {
        await doRevoke();
      }
    } else {
      Alert.alert("Remove partner link?", "This stops all data sharing for this link.", [
        { text: "Cancel", style: "cancel" },
        {
          text: "Remove",
          style: "destructive",
          onPress: doRevoke,
        },
      ]);
    }
  }

  return (
    <KeyboardAwareScrollView
      testID="partner-screen"
      style={styles.screen}
      bottomOffset={24}
      contentContainerStyle={{ paddingBottom: spacing.xxl, paddingTop: insets.top + spacing.md }}
    >
      <Text style={styles.title}>Partner sharing</Text>

      <View style={styles.heroWrap}>
        <Image source={{ uri: media.privacyShield }} style={styles.hero} contentFit="contain" />
      </View>
      <Text style={styles.heroText}>
        Share only what you choose. Partners get a read-only view — and you can revoke access anytime.
      </Text>

      {/* Connect with a partner */}
      <Card style={styles.card} testID="partner-accept-card">
        <Text style={styles.sectionLabel}>Connect with a partner</Text>
        <Text style={styles.helpText}>Enter an invite code your partner shared with you.</Text>
        <View style={styles.codeRow}>
          <TextInput
            testID="partner-code-input"
            value={code}
            onChangeText={setCode}
            placeholder="INVITE CODE"
            placeholderTextColor={colors.text.tertiary}
            autoCapitalize="characters"
            style={styles.codeInput}
          />
          <TouchableOpacity
            testID="partner-accept-button"
            style={styles.acceptBtn}
            onPress={acceptCode}
            disabled={busy}
          >
            <Text style={styles.acceptBtnText}>Link</Text>
          </TouchableOpacity>
        </View>
      </Card>

      {/* Partners I'm viewing */}
      {viewing.length > 0 && (
        <Card style={styles.card} testID="partner-viewing-card">
          <Text style={styles.sectionLabel}>You can view</Text>
          {viewing.map((v) => (
            <TouchableOpacity
              key={v.id}
              testID={`partner-view-${v.id}`}
              style={styles.viewRow}
              onPress={() => router.push(`/partner-view?id=${v.id}&name=${encodeURIComponent(v.owner_name)}`)}
            >
              <View style={styles.avatar}>
                <Ionicons name="person" size={18} color={colors.brand.primary} />
              </View>
              <Text style={styles.viewName}>{v.owner_name}</Text>
              <Ionicons name="chevron-forward" size={18} color={colors.text.tertiary} />
            </TouchableOpacity>
          ))}
        </Card>
      )}

      {/* Sharing my data */}
      <Card style={styles.card} testID="partner-sharing-card">
        <Text style={styles.sectionLabel}>Share my data</Text>
        <Text style={styles.helpText}>
          Generate a code and send it to your partner. Codes expire in 48 hours.
        </Text>
        <View style={{ height: spacing.md }} />
        <PrimaryButton
          testID="partner-share-generate-token-button"
          title="Generate invite code"
          icon="add-circle-outline"
          onPress={generateInvite}
          loading={busy}
        />

        {sharing.map((link) => (
          <View key={link.id} style={styles.linkBlock} testID={`partner-link-${link.id}`}>
            <View style={styles.linkHeader}>
              <View>
                <Text style={styles.linkStatus}>
                  {link.status === "active"
                    ? `Linked with ${link.partner_name || "partner"}`
                    : "Pending — waiting for partner"}
                </Text>
                {link.status !== "active" && (
                  <TouchableOpacity onPress={() => copyToken(link.token)} testID={`copy-token-${link.id}`}>
                    <Text style={styles.tokenText}>{link.token}  ⧉</Text>
                  </TouchableOpacity>
                )}
              </View>
              <TouchableOpacity onPress={() => revoke(link.id)} testID={`revoke-${link.id}`}>
                <Ionicons name="trash-outline" size={20} color={colors.status.error} />
              </TouchableOpacity>
            </View>

            <View style={styles.flags}>
              {FLAG_META.map((f) => (
                <View key={f.key} style={styles.flagRow}>
                  <View style={styles.flagLabelRow}>
                    <Ionicons name={f.icon as any} size={16} color={colors.text.secondary} />
                    <Text style={styles.flagLabel}>{f.label}</Text>
                  </View>
                  <Switch
                    testID={`flag-${f.key}-${link.id}`}
                    value={link.sharing_flags[f.key]}
                    onValueChange={() => toggleFlag(link, f.key)}
                    trackColor={{ true: colors.brand.primary, false: colors.bg.tertiary }}
                    thumbColor="#fff"
                  />
                </View>
              ))}
            </View>

            {link.status === "active" ? (
              <TouchableOpacity
                testID={`partner-space-${link.id}`}
                style={styles.spaceBtn}
                onPress={() =>
                  router.push({
                    pathname: "/partner-space",
                    params: { id: link.id, name: link.partner_name || "" },
                  })
                }
              >
                <Ionicons name="chatbubbles-outline" size={16} color={colors.brand.primary} />
                <Text style={styles.spaceBtnText}>Open shared space</Text>
                <Ionicons name="chevron-forward" size={16} color={colors.brand.primary} />
              </TouchableOpacity>
            ) : null}

            {link.status === "active" ? (
              <View style={styles.emergencyBox}>
                <View style={styles.flagRow}>
                  <View style={styles.flagLabelRow}>
                    <Ionicons name="alert-circle-outline" size={16} color={colors.status.error} />
                    <Text style={styles.flagLabel}>Emergency contact mode</Text>
                  </View>
                  <Switch
                    testID={`emergency-${link.id}`}
                    value={!!link.emergency_contact}
                    onValueChange={(v) => setEmergency(link, v)}
                    trackColor={{ true: colors.status.error, false: colors.bg.tertiary }}
                    thumbColor="#fff"
                  />
                </View>
                <Text style={styles.emergencyHint}>
                  Opt-in. Lets you send important health alerts to {link.partner_name || "this partner"}.
                </Text>
                {link.emergency_contact ? (
                  <TouchableOpacity
                    testID={`send-alert-${link.id}`}
                    style={styles.alertBtn}
                    onPress={() => sendAlert(link)}
                  >
                    <Ionicons name="notifications-outline" size={16} color="#fff" />
                    <Text style={styles.alertBtnText}>Send health alert</Text>
                  </TouchableOpacity>
                ) : null}
              </View>
            ) : null}
          </View>
        ))}
      </Card>

      <View style={styles.infoBanner}>
        <Ionicons name="shield-checkmark-outline" size={16} color={colors.brand.primary} />
        <Text style={styles.infoText}>
          Partners have read-only access. Unshared data is never sent to their device.
        </Text>
      </View>
    </KeyboardAwareScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg.primary },
  title: { ...type.h1, color: colors.text.primary, paddingHorizontal: spacing.screen, marginBottom: spacing.md },
  heroWrap: { alignItems: "center", marginVertical: spacing.sm },
  hero: { width: 120, height: 120 },
  heroText: {
    ...type.body,
    color: colors.text.secondary,
    textAlign: "center",
    paddingHorizontal: spacing.xl,
    marginBottom: spacing.md,
  },
  card: { marginHorizontal: spacing.screen, marginTop: spacing.md },
  sectionLabel: { ...type.caption, color: colors.text.tertiary, marginBottom: spacing.xs },
  helpText: { ...type.bodySm, color: colors.text.secondary },
  codeRow: { flexDirection: "row", marginTop: spacing.md, gap: spacing.sm },
  codeInput: {
    flex: 1,
    backgroundColor: colors.bg.secondary,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 14,
    fontSize: 16,
    letterSpacing: 2,
    color: colors.text.primary,
  },
  acceptBtn: {
    backgroundColor: colors.brand.primary,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    alignItems: "center",
    justifyContent: "center",
  },
  acceptBtnText: { color: "#fff", fontWeight: "600", fontSize: 15 },
  viewRow: { flexDirection: "row", alignItems: "center", paddingVertical: spacing.sm },
  avatar: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.brand.primaryLight,
    alignItems: "center",
    justifyContent: "center",
    marginRight: spacing.md,
  },
  viewName: { ...type.body, color: colors.text.primary, fontWeight: "600", flex: 1 },
  linkBlock: { marginTop: spacing.lg, borderTopWidth: 1, borderTopColor: colors.ui.divider, paddingTop: spacing.md },
  linkHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  linkStatus: { ...type.body, color: colors.text.primary, fontWeight: "600" },
  tokenText: { ...type.h3, color: colors.brand.primary, letterSpacing: 2, marginTop: 4 },
  spaceBtn: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.brand.primaryLight,
    borderRadius: radius.md,
    paddingVertical: 12,
    paddingHorizontal: spacing.md,
    marginTop: spacing.md,
  },
  spaceBtnText: { ...type.body, color: colors.brand.primary, fontWeight: "700", flex: 1, marginLeft: spacing.sm },
  emergencyBox: {
    marginTop: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.ui.divider,
  },
  emergencyHint: { ...type.bodySm, color: colors.text.tertiary, marginTop: 2 },
  alertBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.status.error,
    borderRadius: radius.md,
    paddingVertical: 12,
    marginTop: spacing.sm,
  },
  alertBtnText: { ...type.body, color: "#fff", fontWeight: "700", marginLeft: spacing.sm },
  flags: { marginTop: spacing.sm },
  flagRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 6 },
  flagLabelRow: { flexDirection: "row", alignItems: "center" },
  flagLabel: { ...type.body, color: colors.text.secondary, marginLeft: spacing.sm },
  infoBanner: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.brand.primaryLight,
    marginHorizontal: spacing.screen,
    marginTop: spacing.lg,
    padding: spacing.md,
    borderRadius: radius.md,
  },
  infoText: { ...type.bodySm, color: colors.brand.indigo, marginLeft: spacing.sm, flex: 1 },
});
