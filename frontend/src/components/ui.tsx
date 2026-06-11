import { Ionicons } from "@expo/vector-icons";
import React from "react";
import {
  ActivityIndicator,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
  ViewStyle,
} from "react-native";

import { colors, radius, spacing, type } from "@/src/theme";

export function Card({
  children,
  style,
  highlight,
  testID,
}: {
  children: React.ReactNode;
  style?: ViewStyle;
  highlight?: boolean;
  testID?: string;
}) {
  return (
    <View
      testID={testID}
      style={[highlight ? styles.cardHighlight : styles.card, style]}
    >
      {children}
    </View>
  );
}

export function PrimaryButton({
  title,
  onPress,
  loading,
  disabled,
  testID,
  icon,
  variant = "primary",
}: {
  title: string;
  onPress: () => void;
  loading?: boolean;
  disabled?: boolean;
  testID?: string;
  icon?: keyof typeof Ionicons.glyphMap;
  variant?: "primary" | "secondary" | "danger";
}) {
  const isPrimary = variant === "primary";
  const isDanger = variant === "danger";
  return (
    <TouchableOpacity
      testID={testID}
      activeOpacity={0.7}
      onPress={onPress}
      disabled={disabled || loading}
      style={[
        styles.btn,
        isPrimary && styles.btnPrimary,
        variant === "secondary" && styles.btnSecondary,
        isDanger && styles.btnDanger,
        (disabled || loading) && styles.btnDisabled,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={isPrimary || isDanger ? "#fff" : colors.brand.primary} />
      ) : (
        <View style={styles.btnRow}>
          {icon && (
            <Ionicons
              name={icon}
              size={18}
              color={isPrimary || isDanger ? "#fff" : colors.text.primary}
              style={{ marginRight: 8 }}
            />
          )}
          <Text
            style={[
              styles.btnText,
              { color: isPrimary || isDanger ? "#fff" : colors.text.primary },
            ]}
          >
            {title}
          </Text>
        </View>
      )}
    </TouchableOpacity>
  );
}

export function Chip({
  label,
  selected,
  onPress,
  testID,
}: {
  label: string;
  selected?: boolean;
  onPress?: () => void;
  testID?: string;
}) {
  return (
    <TouchableOpacity
      testID={testID}
      activeOpacity={0.7}
      onPress={onPress}
      style={[styles.chip, selected && styles.chipSelected]}
    >
      <Text style={[styles.chipText, selected && styles.chipTextSelected]}>{label}</Text>
    </TouchableOpacity>
  );
}

export function SectionTitle({ children }: { children: React.ReactNode }) {
  return <Text style={styles.sectionTitle}>{children}</Text>;
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.bg.primary,
    borderRadius: radius.lg,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.ui.border,
  },
  cardHighlight: {
    backgroundColor: colors.brand.primaryLight,
    borderRadius: radius.lg,
    padding: spacing.lg,
  },
  btn: {
    borderRadius: radius.md,
    paddingVertical: 16,
    paddingHorizontal: spacing.lg,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 52,
  },
  btnPrimary: { backgroundColor: colors.brand.primary },
  btnSecondary: { backgroundColor: colors.bg.secondary },
  btnDanger: { backgroundColor: colors.status.error },
  btnDisabled: { opacity: 0.5 },
  btnRow: { flexDirection: "row", alignItems: "center" },
  btnText: { fontSize: 16, fontWeight: "600" },
  chip: {
    backgroundColor: colors.bg.secondary,
    borderRadius: radius.pill,
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderWidth: 1,
    borderColor: colors.ui.border,
  },
  chipSelected: { backgroundColor: colors.brand.primary, borderColor: colors.brand.primary },
  chipText: { color: colors.text.secondary, fontSize: 14, fontWeight: "500" },
  chipTextSelected: { color: "#fff", fontWeight: "600" },
  sectionTitle: { ...type.caption, color: colors.text.tertiary, marginBottom: spacing.md },
});
