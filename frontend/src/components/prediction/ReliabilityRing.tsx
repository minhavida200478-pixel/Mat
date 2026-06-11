import { StyleSheet, Text, View } from "react-native";
import Svg, { Circle } from "react-native-svg";

import { colors, radius, spacing, type } from "@/src/theme";
import { reliabilityColor } from "./helpers";

// Circular gauge for the 0-100 Cycle Reliability Index + classification chip.
export function ReliabilityRing({
  score,
  classification,
}: {
  score: number;
  classification: string;
}) {
  const size = 96;
  const stroke = 9;
  const r = (size - stroke) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const circ = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score)) / 100;
  const color = reliabilityColor(classification);

  return (
    <View style={styles.row} testID="prediction-reliability">
      <Svg width={size} height={size}>
        {/* track */}
        <Circle cx={cx} cy={cy} r={r} stroke={colors.bg.tertiary} strokeWidth={stroke} fill="none" />
        {/* progress */}
        <Circle
          cx={cx}
          cy={cy}
          r={r}
          stroke={color}
          strokeWidth={stroke}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={`${circ * pct} ${circ}`}
          transform={`rotate(-90 ${cx} ${cy})`}
        />
      </Svg>
      <View style={styles.center}>
        <Text style={[styles.score, { color }]} testID="prediction-reliability-score">
          {score}
        </Text>
        <Text style={styles.outOf}>/ 100</Text>
      </View>
      <View style={styles.meta}>
        <View style={[styles.chip, { backgroundColor: color + "22" }]} testID="prediction-reliability-chip">
          <Text style={[styles.chipText, { color }]}>{classification}</Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", marginTop: spacing.sm },
  center: { position: "absolute", left: 0, width: 96, height: 96, alignItems: "center", justifyContent: "center", pointerEvents: "none" },
  score: { fontSize: 26, fontWeight: "800", letterSpacing: -0.5 },
  outOf: { ...type.caption, color: colors.text.tertiary, marginTop: -2 },
  meta: { flex: 1, marginLeft: spacing.lg, alignItems: "flex-start" },
  chip: { borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 4 },
  chipText: { ...type.caption, fontWeight: "700", textTransform: "none" },
});
