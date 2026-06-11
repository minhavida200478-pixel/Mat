import { StyleSheet, View } from "react-native";

import { colors, spacing } from "@/src/theme";
import { daysBetween } from "./helpers";

// Horizontal fertile-window bar with an ovulation marker positioned within it.
export function FertileBar({
  start,
  end,
  ovulation,
}: {
  start: string;
  end: string;
  ovulation: string | null;
}) {
  const span = Math.max(1, daysBetween(start, end)); // inclusive-ish span in days
  const ovuOffset = ovulation ? daysBetween(start, ovulation) : null;
  const ovuPct = ovuOffset != null ? Math.min(100, Math.max(0, (ovuOffset / span) * 100)) : null;

  return (
    <View style={styles.wrap} testID="prediction-fertile-bar">
      <View style={styles.track}>
        <View style={styles.fill} />
        {ovuPct != null ? (
          <View style={[styles.marker, { left: `${ovuPct}%` }]} testID="prediction-ovulation-marker" />
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginVertical: spacing.xs },
  track: {
    height: 14,
    borderRadius: 7,
    backgroundColor: colors.status.fertileLight,
    justifyContent: "center",
    overflow: "hidden",
  },
  fill: {
    ...StyleSheet.absoluteFillObject,
    borderRadius: 7,
    backgroundColor: colors.status.fertile,
    opacity: 0.35,
  },
  marker: {
    position: "absolute",
    width: 12,
    height: 12,
    borderRadius: 6,
    marginLeft: -6,
    backgroundColor: colors.status.fertile,
    borderWidth: 2,
    borderColor: "#fff",
  },
});
