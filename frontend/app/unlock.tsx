import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { PrimaryButton } from "@/src/components/ui";
import { useAuth } from "@/src/ctx/AuthContext";
import { colors, spacing, type } from "@/src/theme";

export default function Unlock() {
  const { tryUnlock, signOut } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [failed, setFailed] = useState(false);

  async function attempt() {
    setFailed(false);
    const ok = await tryUnlock();
    if (ok) router.replace("/(tabs)");
    else setFailed(true);
  }

  useEffect(() => {
    attempt();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSignOut() {
    await signOut();
    router.replace("/(auth)/login");
  }

  return (
    <View style={[styles.container, { paddingTop: insets.top }]} testID="unlock-screen">
      <View style={styles.center}>
        <View style={styles.iconCircle}>
          <Ionicons name="finger-print" size={48} color={colors.brand.primary} />
        </View>
        <Text style={styles.title}>Cycle is locked</Text>
        <Text style={styles.subtitle}>
          Use Face ID or fingerprint to unlock your private health data.
        </Text>
        {failed ? (
          <Text style={styles.failed} testID="unlock-failed-text">
            Unlock cancelled. Try again to continue.
          </Text>
        ) : null}
      </View>
      <View style={[styles.actions, { paddingBottom: insets.bottom + spacing.lg }]}>
        <PrimaryButton
          testID="unlock-button"
          title="Unlock"
          icon="lock-open-outline"
          onPress={attempt}
        />
        <View style={{ height: spacing.sm }} />
        <PrimaryButton
          testID="unlock-signout-button"
          title="Sign out instead"
          variant="secondary"
          onPress={handleSignOut}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg.primary, paddingHorizontal: spacing.screen },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  iconCircle: {
    width: 96,
    height: 96,
    borderRadius: 48,
    backgroundColor: colors.brand.primaryLight,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.lg,
  },
  title: { ...type.h2, color: colors.text.primary },
  subtitle: {
    ...type.body,
    color: colors.text.secondary,
    textAlign: "center",
    marginTop: spacing.sm,
    paddingHorizontal: spacing.lg,
  },
  failed: { ...type.bodySm, color: colors.status.error, marginTop: spacing.md },
  actions: {},
});
