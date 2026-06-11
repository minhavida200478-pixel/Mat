import React from "react";
import { StyleSheet, Text, View } from "react-native";
import Svg, { Circle, Defs, LinearGradient, Stop } from "react-native-svg";

import { colors, type } from "@/src/theme";

type Props = {
  cycleDay: number;
  cycleLength: number;
  phaseLabel: string;
  subLabel: string;
  size?: number;
};

export default function CycleRing({
  cycleDay,
  cycleLength,
  phaseLabel,
  subLabel,
  size = 240,
}: Props) {
  const stroke = 16;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = Math.max(0, Math.min(1, cycleDay / Math.max(cycleLength, 1)));
  const dashOffset = circumference * (1 - progress);

  return (
    <View style={[styles.wrap, { width: size, height: size }]} testID="cycle-ring">
      <Svg width={size} height={size}>
        <Defs>
          <LinearGradient id="ringGrad" x1="0" y1="0" x2="1" y2="1">
            <Stop offset="0" stopColor={colors.brand.primary} />
            <Stop offset="1" stopColor={colors.status.fertile} />
          </LinearGradient>
        </Defs>
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={colors.bg.tertiary}
          strokeWidth={stroke}
          fill="none"
        />
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="url(#ringGrad)"
          strokeWidth={stroke}
          strokeLinecap="round"
          fill="none"
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </Svg>
      <View style={styles.center}>
        <Text style={styles.dayLabel}>Day</Text>
        <Text style={styles.dayValue} testID="cycle-day-value">
          {cycleDay > 0 ? cycleDay : "—"}
        </Text>
        <Text style={styles.phase}>{phaseLabel}</Text>
        <Text style={styles.sub}>{subLabel}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: "center", justifyContent: "center" },
  center: { position: "absolute", alignItems: "center" },
  dayLabel: { ...type.caption, color: colors.text.tertiary },
  dayValue: { fontSize: 56, fontWeight: "700", color: colors.text.primary, lineHeight: 60 },
  phase: { ...type.h3, color: colors.brand.primary, marginTop: 4 },
  sub: { ...type.bodySm, color: colors.text.secondary, marginTop: 2 },
});
