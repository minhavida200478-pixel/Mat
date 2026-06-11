import { Ionicons } from "@expo/vector-icons";
import { Link, useLocalSearchParams, useRouter } from "expo-router";
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
import { PREDICTION_DISCLAIMER } from "@/src/constants";
import { useAuth } from "@/src/ctx/AuthContext";
import { colors, radius, spacing, type } from "@/src/theme";

export default function Login() {
  const { signIn } = useAuth();
  const router = useRouter();
  const params = useLocalSearchParams<{ reset?: string }>();
  const insets = useSafeAreaInsets();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleLogin() {
    setError("");
    if (!email || !password) {
      setError("Please enter your email and password.");
      return;
    }
    setLoading(true);
    try {
      await signIn(email.trim(), password);
      router.replace("/(tabs)");
    } catch (e: any) {
      // 403 == account exists but email isn't verified yet. Route to verification.
      if (e?.status === 403) {
        router.push({
          pathname: "/(auth)/verify-email",
          params: { email: email.trim() },
        });
        return;
      }
      setError(e?.message || "Login failed. Please try again.");
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
        <View style={styles.brandRow}>
          <View style={styles.logoCircle}>
            <Ionicons name="ellipse" size={22} color={colors.brand.primary} />
          </View>
          <Text style={styles.brand}>Cycle</Text>
        </View>
        <Text style={styles.title}>Welcome back</Text>
        <Text style={styles.subtitle}>
          Your private, medical-grade cycle companion.
        </Text>

        <View style={styles.card}>
          {params.reset === "1" ? (
            <Text style={styles.success} testID="reset-success-banner">
              Password updated. Sign in with your new password.
            </Text>
          ) : null}
          {error ? (
            <Text style={styles.error} testID="login-error">
              {error}
            </Text>
          ) : null}
          <Text style={styles.label}>Email</Text>
          <TextInput
            testID="login-email-input"
            value={email}
            onChangeText={setEmail}
            placeholder="you@example.com"
            placeholderTextColor={colors.text.tertiary}
            autoCapitalize="none"
            keyboardType="email-address"
            style={styles.input}
          />
          <Text style={styles.label}>Password</Text>
          <TextInput
            testID="login-password-input"
            value={password}
            onChangeText={setPassword}
            placeholder="••••••••"
            placeholderTextColor={colors.text.tertiary}
            secureTextEntry
            style={styles.input}
          />
          <TouchableOpacity
            testID="forgot-password-link"
            style={styles.forgotRow}
            onPress={() => router.push("/(auth)/forgot-password")}
          >
            <Text style={styles.link}>Forgot password?</Text>
          </TouchableOpacity>
          <View style={{ height: spacing.md }} />
          <PrimaryButton
            testID="login-submit-button"
            title="Sign In"
            onPress={handleLogin}
            loading={loading}
          />
          <View style={styles.footerRow}>
            <Text style={styles.footerText}>New here? </Text>
            <Link href="/(auth)/register" replace testID="go-to-register-link">
              <Text style={styles.link}>Create an account</Text>
            </Link>
          </View>
        </View>

        <View style={styles.privacyRow}>
          <Ionicons name="lock-closed" size={14} color={colors.text.tertiary} />
          <Text style={styles.disclaimer}>{PREDICTION_DISCLAIMER}</Text>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  bg: { flex: 1, backgroundColor: colors.bg.primary },
  scroll: { flex: 1 },
  content: { flexGrow: 1, paddingHorizontal: spacing.screen, justifyContent: "center" },
  brandRow: { flexDirection: "row", alignItems: "center", marginBottom: spacing.xl },
  logoCircle: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.brand.primaryLight,
    alignItems: "center",
    justifyContent: "center",
    marginRight: spacing.sm,
  },
  brand: { ...type.h2, color: colors.text.primary },
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
  success: {
    color: colors.brand.primary,
    backgroundColor: colors.brand.primaryLight,
    padding: spacing.sm,
    borderRadius: radius.sm,
    marginBottom: spacing.md,
    fontSize: 14,
  },
  forgotRow: { alignSelf: "flex-end", marginTop: -spacing.xs, marginBottom: spacing.xs },
  footerRow: { flexDirection: "row", justifyContent: "center", marginTop: spacing.lg },
  footerText: { color: colors.text.secondary, fontSize: 14 },
  link: { color: colors.brand.primary, fontSize: 14, fontWeight: "600" },
  privacyRow: { flexDirection: "row", alignItems: "center", justifyContent: "center", marginTop: spacing.xl },
  disclaimer: { ...type.bodySm, color: colors.text.tertiary, marginLeft: 6, textAlign: "center" },
});
