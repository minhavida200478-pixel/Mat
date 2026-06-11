import { Ionicons } from "@expo/vector-icons";
import { Link, useRouter } from "expo-router";
import { useState } from "react";
import { StyleSheet, Text, TextInput, View } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { PrimaryButton } from "@/src/components/ui";
import { useAuth } from "@/src/ctx/AuthContext";
import { colors, radius, spacing, type } from "@/src/theme";

export default function Register() {
  const { signUp } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleRegister() {
    setError("");
    if (!email || !password) {
      setError("Email and password are required.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setLoading(true);
    try {
      await signUp(email.trim(), password, fullName.trim());
      router.push({
        pathname: "/(auth)/verify-email",
        params: { email: email.trim() },
      });
    } catch (e: any) {
      setError(e?.message || "Registration failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <View style={styles.bg}>
      <KeyboardAwareScrollView
        style={styles.scroll}
        bottomOffset={24}
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
        <Text style={styles.title}>Create account</Text>
        <Text style={styles.subtitle}>Private by design. Your data stays yours.</Text>

        <View style={styles.card}>
          {error ? (
            <Text style={styles.error} testID="register-error">
              {error}
            </Text>
          ) : null}
          <Text style={styles.label}>Name (optional)</Text>
          <TextInput
            testID="register-name-input"
            value={fullName}
            onChangeText={setFullName}
            placeholder="Your name"
            placeholderTextColor={colors.text.tertiary}
            style={styles.input}
          />
          <Text style={styles.label}>Email</Text>
          <TextInput
            testID="register-email-input"
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
            testID="register-password-input"
            value={password}
            onChangeText={setPassword}
            placeholder="At least 8 characters"
            placeholderTextColor={colors.text.tertiary}
            secureTextEntry
            style={styles.input}
          />
          <View style={{ height: spacing.md }} />
          <PrimaryButton
            testID="register-submit-button"
            title="Create Account"
            onPress={handleRegister}
            loading={loading}
          />
          <View style={styles.footerRow}>
            <Text style={styles.footerText}>Already have an account? </Text>
            <Link href="/(auth)/login" replace testID="go-to-login-link">
              <Text style={styles.link}>Sign in</Text>
            </Link>
          </View>
        </View>
      </KeyboardAwareScrollView>
    </View>
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
  footerRow: { flexDirection: "row", justifyContent: "center", marginTop: spacing.lg },
  footerText: { color: colors.text.secondary, fontSize: 14 },
  link: { color: colors.brand.primary, fontSize: 14, fontWeight: "600" },
});
