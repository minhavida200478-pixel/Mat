// Accuracy-over-time view (P2): surfaces the stored /api/prediction/history
// trail — back-tested validation metrics + how confidence & reliability have
// evolved across stored predictions.
import { Ionicons } from "@expo/vector-icons";
import { StyleSheet, Text, View } from "react-native";
import Svg, { Circle, Path } from "react-native-svg";

import { Card } from "@/src/components/ui";
import { colors, spacing, type } from "@/src/theme";

import { confidenceColor, MONTHS, reliabilityColor } from "./helpers";

export type PredictionHistoryRow = {
  prediction_id: string;
  predicted_period_start: string | null;
  confidence: number | null;
  reliability_score: number | null;
  reliability_classification: string | null;
  updated_at?: string;
  generated_at?: string;
};

export type ValidationMetricsSnapshot = {
  metrics: {
    mae: number | null;
    rmse: number | null;
    success_rate: number | null;
    stability_score: number | null;
    samples: number;
  } | null;
  benchmark_accuracy?: number | null;
  prediction_errors?: {
    rolling_3_cycle_error: number | null;
    rolling_6_cycle_error: number | null;
    rolling_12_cycle_error: number | null;
    bias_days: number | null;
  } | null;
} | null;

export type PredictionHistory = {
  history: PredictionHistoryRow[];
  count: number;
  validationMetrics: ValidationMetricsSnapshot;
};

const CHART_W = 280;
const CHART_H = 72;

function fmtShort(iso?: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${MONTHS[d.getMonth()]} ${d.getDate()}`;
}

// Build an SVG polyline path for a 0-100 series.
function linePath(values: number[]): string {
  if (values.length === 0) return "";
  const stepX = values.length > 1 ? CHART_W / (values.length - 1) : 0;
  return values
    .map((v, i) => {
      const x = values.length > 1 ? i * stepX : CHART_W / 2;
      const y = CHART_H - (Math.max(0, Math.min(100, v)) / 100) * CHART_H;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

export function AccuracyTrail({ data }: { data: PredictionHistory | null }) {
  if (!data) return null;

  const m = data.validationMetrics?.metrics ?? null;
  // Oldest -> newest for the chart (API returns newest first).
  const rows = [...data.history].reverse();
  const confSeries = rows
    .map((r) => r.confidence)
    .filter((v): v is number => typeof v === "number");
  const relSeries = rows
    .map((r) => r.reliability_score)
    .filter((v): v is number => typeof v === "number");

  const hasMetrics = m != null && m.samples > 0;
  const hasTrail = confSeries.length >= 2 || relSeries.length >= 2;
  const latest = data.history[0] ?? null;

  return (
    <Card style={styles.card} testID="prediction-accuracy-card">
      <View style={styles.header}>
        <Ionicons name="analytics-outline" size={16} color={colors.brand.primary} />
        <Text style={styles.headerTitle}>Prediction accuracy</Text>
      </View>

      {hasMetrics ? (
        <View style={styles.metricRow} testID="accuracy-metrics">
          <Metric
            testID="accuracy-mae"
            value={m.mae != null ? `±${m.mae}` : "—"}
            unit="days"
            label="Avg error"
          />
          <Metric
            testID="accuracy-success"
            value={m.success_rate != null ? `${Math.round(m.success_rate)}%` : "—"}
            unit=""
            label="Hit rate"
            color={m.success_rate != null ? confidenceColor(m.success_rate) : undefined}
          />
          <Metric
            testID="accuracy-stability"
            value={m.stability_score != null ? `${Math.round(m.stability_score)}` : "—"}
            unit="/100"
            label="Stability"
          />
        </View>
      ) : null}

      {hasTrail ? (
        <View style={styles.chartWrap} testID="accuracy-trail-chart">
          <Svg width="100%" height={CHART_H + 8} viewBox={`0 -4 ${CHART_W} ${CHART_H + 8}`}>
            {relSeries.length >= 2 ? (
              <Path
                d={linePath(relSeries)}
                stroke={reliabilityColor(latest?.reliability_classification ?? "Moderate")}
                strokeWidth={2}
                strokeLinecap="round"
                fill="none"
                opacity={0.45}
              />
            ) : null}
            {confSeries.length >= 2 ? (
              <Path
                d={linePath(confSeries)}
                stroke={colors.brand.primary}
                strokeWidth={2.5}
                strokeLinecap="round"
                fill="none"
              />
            ) : null}
            {confSeries.length >= 2 ? (
              <Circle
                cx={CHART_W}
                cy={CHART_H - (Math.max(0, Math.min(100, confSeries[confSeries.length - 1])) / 100) * CHART_H}
                r={4}
                fill={colors.brand.primary}
              />
            ) : null}
          </Svg>
          <View style={styles.axisRow}>
            <Text style={styles.axisText}>{fmtShort(rows[0]?.generated_at ?? rows[0]?.updated_at)}</Text>
            <Text style={styles.axisText}>
              {fmtShort(rows[rows.length - 1]?.generated_at ?? rows[rows.length - 1]?.updated_at)}
            </Text>
          </View>
          <View style={styles.legendRow}>
            <View style={styles.legendItem}>
              <View style={[styles.legendDot, { backgroundColor: colors.brand.primary }]} />
              <Text style={styles.legendText}>Confidence</Text>
            </View>
            {relSeries.length >= 2 ? (
              <View style={styles.legendItem}>
                <View
                  style={[
                    styles.legendDot,
                    {
                      backgroundColor: reliabilityColor(latest?.reliability_classification ?? "Moderate"),
                      opacity: 0.45,
                    },
                  ]}
                />
                <Text style={styles.legendText}>Reliability</Text>
              </View>
            ) : null}
          </View>
        </View>
      ) : null}

      {!hasMetrics && !hasTrail ? (
        <Text style={styles.empty} testID="accuracy-empty">
          Accuracy tracking builds over time — every time your cycle history changes,
          the engine stores a snapshot here so you can see how predictions improve.
        </Text>
      ) : (
        <Text style={styles.hint}>
          {hasMetrics
            ? `Back-tested on ${m!.samples} past cycle${m!.samples === 1 ? "" : "s"}: average miss, % predicted within a few days, and how steady the errors are.`
            : "How confidence and reliability have evolved across stored predictions."}
        </Text>
      )}
    </Card>
  );
}

function Metric({
  value,
  unit,
  label,
  color,
  testID,
}: {
  value: string;
  unit: string;
  label: string;
  color?: string;
  testID?: string;
}) {
  return (
    <View style={styles.metric} testID={testID}>
      <Text style={[styles.metricValue, color ? { color } : null]}>
        {value}
        {unit ? <Text style={styles.metricUnit}> {unit}</Text> : null}
      </Text>
      <Text style={styles.metricLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { marginHorizontal: spacing.screen, marginTop: spacing.md },
  header: { flexDirection: "row", alignItems: "center", marginBottom: spacing.sm },
  headerTitle: { ...type.h3, color: colors.text.primary, marginLeft: spacing.sm, flex: 1 },

  metricRow: { flexDirection: "row", marginTop: spacing.xs },
  metric: { flex: 1 },
  metricValue: { ...type.h2, color: colors.text.primary, fontWeight: "700" },
  metricUnit: { ...type.bodySm, color: colors.text.tertiary, fontWeight: "400" },
  metricLabel: { ...type.caption, color: colors.text.tertiary, marginTop: 2 },

  chartWrap: { marginTop: spacing.md },
  axisRow: { flexDirection: "row", justifyContent: "space-between", marginTop: 2 },
  axisText: { ...type.caption, color: colors.text.tertiary, textTransform: "none" },
  legendRow: { flexDirection: "row", gap: spacing.md, marginTop: spacing.sm },
  legendItem: { flexDirection: "row", alignItems: "center" },
  legendDot: { width: 8, height: 8, borderRadius: 4, marginRight: 5 },
  legendText: { ...type.caption, color: colors.text.secondary },

  empty: { ...type.bodySm, color: colors.text.secondary, lineHeight: 19, marginTop: spacing.xs },
  hint: { ...type.caption, color: colors.text.tertiary, marginTop: spacing.sm, textTransform: "none", lineHeight: 16 },
});
