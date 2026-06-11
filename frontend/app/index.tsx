import { Redirect } from "expo-router";
import { ActivityIndicator, StyleSheet, View } from "react-native";

import { useAuth } from "@/src/ctx/AuthContext";
import { colors } from "@/src/theme";

export default function Index() {
  const { user, loading, locked } = useAuth();

  if (loading) {
    return (
      <View style={styles.container} testID="boot-loader">
        <ActivityIndicator size="large" color={colors.brand.primary} />
      </View>
    );
  }

  if (locked) return <Redirect href="/unlock" />;
  if (user) return <Redirect href="/(tabs)" />;
  return <Redirect href="/(auth)/login" />;
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg.primary,
    alignItems: "center",
    justifyContent: "center",
  },
});
