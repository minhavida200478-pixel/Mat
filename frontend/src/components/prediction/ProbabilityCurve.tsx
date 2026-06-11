import { Dimensions, StyleSheet, Text, View } from "react-native";
import Svg, { Circle, Defs, Line, LinearGradient, Path, Rect, Stop } from "react-native-svg";

import { colors, spacing, type } from "@/src/theme";
import { fmtDate } from "./helpers";
import type { ProbPoint } from "./types";

// Per-day Gaussian probability curve centred on the predicted next-period date.
export function ProbabilityCurve({ points, accent }: { points: ProbPoint[]; accent: string }) {
  const screenW = Dimensions.get("window").width;
  // Card sits inside screen padding (spacing.screen each side) with internal padding (spacing.lg each side).
  const W = Math.max(220, screenW - spacing.screen * 2 - spacing.lg * 2);
  const H = 120;
  const padBottom = 22;
  const padTop = 10;
  const chartH = H - padBottom - padTop;

  const n = points.length;
  const maxP = Math.max(1, ...points.map((p) => p.probability));
  const x = (i: number) => (n === 1 ? W / 2 : (i / (n - 1)) * W);
  const y = (prob: number) => padTop + chartH - (prob / maxP) * chartH;

  const linePath = points
    .map((pt, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(pt.probability).toFixed(1)}`)
    .join(" ");
  const areaPath =
    `${linePath} L ${x(n - 1).toFixed(1)} ${(padTop + chartH).toFixed(1)} ` +
    `L ${x(0).toFixed(1)} ${(padTop + chartH).toFixed(1)} Z`;

  const peakIdx = points.reduce((best, pt, i) => (pt.probability > points[best].probability ? i : best), 0);
  const peak = points[peakIdx];

  const firstPt = points[0];
  const lastPt = points[n - 1];

  return (
    <View style={{ marginTop: spacing.sm }}>
      <Svg width={W} height={H} testID="prediction-prob-curve">
        <Defs>
          <LinearGradient id="probFill" x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor={accent} stopOpacity={0.28} />
            <Stop offset="1" stopColor={accent} stopOpacity={0.02} />
          </LinearGradient>
        </Defs>

        {/* baseline */}
        <Line x1={0} y1={padTop + chartH} x2={W} y2={padTop + chartH} stroke={colors.ui.divider} strokeWidth={1} />

        {/* peak (predicted) vertical guide */}
        <Line x1={x(peakIdx)} y1={padTop} x2={x(peakIdx)} y2={padTop + chartH} stroke={accent} strokeWidth={1} strokeDasharray="3 3" opacity={0.5} />

        {/* area + line */}
        <Path d={areaPath} fill="url(#probFill)" />
        <Path d={linePath} fill="none" stroke={accent} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />

        {/* peak marker */}
        <Circle cx={x(peakIdx)} cy={y(peak.probability)} r={4.5} fill={accent} stroke="#fff" strokeWidth={2} />

        {/* x-axis label ticks at first / peak / last */}
        <Rect x={x(peakIdx) - 1} y={padTop + chartH} width={2} height={3} fill={accent} />
      </Svg>

      <View style={styles.axis}>
        <Text style={styles.axisLabel}>{fmtDate(firstPt.date)}</Text>
        <Text style={[styles.axisLabel, styles.axisPeak]}>{fmtDate(peak.date)} · {peak.probability}%</Text>
        <Text style={styles.axisLabel}>{fmtDate(lastPt.date)}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  axis: { flexDirection: "row", justifyContent: "space-between", marginTop: 6 },
  axisLabel: { ...type.caption, color: colors.text.tertiary, textTransform: "none" },
  axisPeak: { color: colors.text.secondary, fontWeight: "700" },
});
