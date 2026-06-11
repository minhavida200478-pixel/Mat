import { StyleSheet, Text, View } from "react-native";

import { colors, spacing, type } from "@/src/theme";
import { fmtDate } from "./helpers";
import type { PredictionIntervals } from "./types";

// Nested P50/P75/P90/P95 prediction-interval bands (wider = more certainty).
export function IntervalBands({
  intervals,
  accent,
}: {
  intervals: PredictionIntervals;
  accent: string;
}) {
  const levels: { key: "p50" | "p75" | "p90" | "p95"; label: string }[] = [
    { key: "p50", label: "50%" },
    { key: "p75", label: "75%" },
    { key: "p90", label: "90%" },
    { key: "p95", label: "95%" },
  ];
  const maxHw = Math.max(
    1,
    ...levels.map((l) => intervals[l.key]?.half_width_days ?? 0),
  );

  return (
    <View style={{ marginTop: spacing.sm }}>
      {levels.map((l, i) => {
        const band = intervals[l.key];
        if (!band) return null;
        const widthPct = Math.max(12, (band.half_width_days / maxHw) * 100);
        const opacity = 0.22 + i * 0.16;
        return (
          <View key={l.key} style={styles.row} testID={`prediction-interval-${l.key}`}>
            <Text style={styles.label}>{l.label}</Text>
            <View style={styles.track}>
              <View
                style={[
                  styles.fill,
                  { width: `${widthPct}%`, backgroundColor: accent, opacity },
                ]}
              />
            </View>
            <Text style={styles.range}>
              {fmtDate(band.start)} – {fmtDate(band.end)} (±{band.half_width_days}d)
            </Text>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", marginTop: spacing.sm },
  label: { ...type.caption, color: colors.text.secondary, fontWeight: "700", width: 34 },
  track: { width: 64, height: 8, borderRadius: 4, backgroundColor: colors.bg.tertiary, overflow: "hidden", marginRight: spacing.sm },
  fill: { height: 8, borderRadius: 4 },
  range: { ...type.caption, color: colors.text.tertiary, flex: 1, textTransform: "none" },
});
