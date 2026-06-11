import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
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

import { api } from "@/src/api/client";
import { PrimaryButton } from "@/src/components/ui";
import { colors, radius, spacing, type } from "@/src/theme";

export default function ForgotPassword() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [step, setStep] = useState<"request" | "reset">("request");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [loading, setLoading] = useState(false);

  async function requestCode() {
    setError("");
    setInfo("");
    if (!email.trim()) {
      setError("Please enter your email.");
      return;
    }
    setLoading(true);
    try {
      await api.post("/auth/forgot-password", { email: email.trim() }, false);
      setInfo("If an account exists for that email, a reset code has been sent. Enter it below.");
      setStep("reset");
    } catch (e: any) {
      setError(e?.message || "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function submitReset() {
    setError("");
    if (!code.trim() || !newPassword) {
      setError("Enter the code and your new password.");
      return;
    }
    if (newPassword.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setLoading(true);
    try {
      await api.post(
        "/auth/reset-password",
        { email: email.trim(), code: code.trim(), new_password: newPassword },
        false,
      );
      router.replace({ pathname: "/(auth)/login", params: { reset: "1" } });
    } catch (e: any) {
      setError(e?.message || "Could not reset password. Please try again.");
    } finally {
      setLoading(false);
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
          testID="forgot-back-button"
          style={styles.backBtn}
          onPress={() => router.replace("/(auth)/login")}
        >
          <Ionicons name="chevron-back" size={22} color={colors.text.primary} />
          <Text style={styles.backText}>Back to sign in</Text>
        </TouchableOpacity>

        <Text style={styles.title}>
          {step === "request" ? "Reset password" : "Enter your code"}
        </Text>
        <Text style={styles.subtitle}>
          {step === "request"
            ? "We'll email you a secure code to reset your password."
            : "Check your email for the 6-digit code, then set a new password."}
        </Text>

        <View style={styles.card}>
          {error ? (
            <Text style={styles.error} testID="forgot-error">{error}</Text>
          ) : null}
          {info ? (
            <Text style={styles.info} testID="forgot-info">{info}</Text>
          ) : null}

          {step === "request" ? (
            <>
              <Text style={styles.label}>Email</Text>
              <TextInput
                testID="forgot-email-input"
                value={email}
                onChangeText={setEmail}
                placeholder="you@example.com"
                placeholderTextColor={colors.text.tertiary}
                autoCapitalize="none"
                keyboardType="email-address"
                style={styles.input}
              />
              <View style={{ height: spacing.sm }} />
              <PrimaryButton
                testID="forgot-request-button"
                title="Send reset code"
                onPress={requestCode}
                loading={loading}
              />
            </>
          ) : (
            <>
              <Text style={styles.label}>Reset code</Text>
              <TextInput
                testID="forgot-code-input"
                value={code}
                onChangeText={setCode}
                placeholder="123456"
                placeholderTextColor={colors.text.tertiary}
                keyboardType="number-pad"
                maxLength={6}
                style={styles.input}
              />
              <Text style={styles.label}>New password</Text>
              <TextInput
                testID="forgot-new-password-input"
                value={newPassword}
                onChangeText={setNewPassword}
                placeholder="At least 8 characters"
                placeholderTextColor={colors.text.tertiary}
                secureTextEntry
                style={styles.input}
              />
              <View style={{ height: spacing.sm }} />
              <PrimaryButton
                testID="forgot-reset-button"
                title="Update password"
                onPress={submitReset}
                loading={loading}
              />
              <TouchableOpacity
                testID="forgot-resend-button"
                style={styles.resend}
                onPress={requestCode}
                disabled={loading}
              >
                <Text style={styles.link}>Resend code</Text>
              </TouchableOpacity>
            </>
          )}
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
