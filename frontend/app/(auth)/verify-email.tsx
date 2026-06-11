import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { PrimaryButton } from "@/src/components/ui";
import { useAuth } from "@/src/ctx/AuthContext";
import { colors, radius, spacing, type } from "@/src/theme";

export default function VerifyEmail() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { verifyEmail, resendVerification } = useAuth();
  const params = useLocalSearchParams<{ email?: string }>();
  const email = (params.email || "").trim();

  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState(
    "We've sent a 6-digit verification code to your email. Enter it below to finish setting up your account.",
  );
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);

  async function submitCode() {
    setError("");
    if (!code.trim()) {
      setError("Please enter the verification code.");
      return;
    }
    setLoading(true);
    try {
      await verifyEmail(email, code.trim());
      router.replace("/(tabs)");
    } catch (e: any) {
      setError(e?.message || "Could not verify your email. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function resend() {
    setError("");
    setInfo("");
    setResending(true);
    try {
      await resendVerification(email);
      setInfo("If your account still needs verification, a new code has been sent.");
    } catch (e: any) {
      setError(e?.message || "Could not resend the code. Please try again.");
    } finally {
      setResending(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.bg}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={[
          styles.content,
          { paddingTop: insets.top + 48, paddingBottom: insets.bottom + 32 },
        ]}
        keyboardShouldPersistTaps="handled"
      >
        <TouchableOpacity
          testID="verify-back-button"
          style={styles.backBtn}
          onPress={() => router.replace("/(auth)/login")}
        >
          <Ionicons name="chevron-back" size={22} color={colors.text.primary} />
          <Text style={styles.backText}>Back to sign in</Text>
        </TouchableOpacity>

        <Text style={styles.title}>Verify your email</Text>
        <Text style={styles.subtitle}>
          {email ? `Code sent to ${email}` : "Enter the code we emailed you."}
        </Text>

        <View style={styles.card}>
          {error ? (
            <Text style={styles.error} testID="verify-error">{error}</Text>
          ) : null}
          {info ? (
            <Text style={styles.info} testID="verify-info">{info}</Text>
          ) : null}

          <Text style={styles.label}>Verification code</Text>
          <TextInput
            testID="verify-code-input"
            value={code}
            onChangeText={setCode}
            placeholder="123456"
            placeholderTextColor={colors.text.tertiary}
            keyboardType="number-pad"
            maxLength={6}
            style={styles.input}
          />
          <View style={{ height: spacing.sm }} />
          <PrimaryButton
            testID="verify-submit-button"
            title="Verify & continue"
            onPress={submitCode}
            loading={loading}
          />
          <TouchableOpacity
            testID="verify-resend-button"
            style={styles.resend}
            onPress={resend}
            disabled={resending}
          >
            <Text style={styles.link}>
              {resending ? "Sending…" : "Didn't get a code? Resend"}
            </Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  bg: { flex: 1, backgroundColor: colors.bg.primary },
  scroll: { flex: 1 },
  content: { flexGrow: 1, paddingHorizontal: spacing.screen, justifyContent: "center" },
  backBtn: { flexDirection: "row", alignItems: "center", marginBottom: spacing.xl },
  backText: { ...type.body, color: colors.text.primary, marginLeft: 2 },
  title: { ...type.h1, color: colors.text.primary },
  subtitle: { ...type.body, color: colors.text.secondary, marginTop: spacing.sm, marginBottom: spacing.xl },
  card: {
    backgroundColor: colors.bg.primary,
    borderRadius: radius.lg,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.ui.border,
  },
  label: { ...type.caption, color: colors.text.tertiary, marginBottom: spacing.xs },
  input: {
    backgroundColor: colors.bg.secondary,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 14,
    fontSize: 16,
    color: colors.text.primary,
    marginBottom: spacing.md,
    borderWidth: 1,
    borderColor: "transparent",
    letterSpacing: 4,
  },
  error: {
    color: colors.status.error,
    backgroundColor: colors.status.periodLight,
    padding: spacing.sm,
    borderRadius: radius.sm,
    marginBottom: spacing.md,
    fontSize: 14,
  },
  info: {
    color: colors.brand.primary,
    backgroundColor: colors.brand.primaryLight,
    padding: spacing.sm,
    borderRadius: radius.sm,
    marginBottom: spacing.md,
    fontSize: 14,
  },
  resend: { alignItems: "center", marginTop: spacing.lg },
  link: { color: colors.brand.primary, fontSize: 14, fontWeight: "600" },
});
