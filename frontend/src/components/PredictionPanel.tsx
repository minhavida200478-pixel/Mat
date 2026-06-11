import { Ionicons } from "@expo/vector-icons";
import { StyleSheet, Text, View } from "react-native";

import { Card } from "@/src/components/ui";
import { colors, radius, spacing, type } from "@/src/theme";

import { FertileBar } from "./prediction/FertileBar";
import { IntervalBands } from "./prediction/IntervalBands";
import { ProbabilityCurve } from "./prediction/ProbabilityCurve";
import { ReliabilityRing } from "./prediction/ReliabilityRing";
import { confidenceColor, fmtDate } from "./prediction/helpers";
import type { Prediction } from "./prediction/types";

// Re-export types so existing importers keep working.
export type {
  Prediction,
  ProbPoint,
  HealthFlag,
  TrendInsight,
  ReliabilityIndex,
  IntervalBand,
  PredictionIntervals,
  DataSufficiency,
} from "./prediction/types";

const REGULARITY_COLOR: Record<string, string> = {
  "Very Regular": colors.status.success,
  Regular: colors.brand.primary,
  "Moderately Irregular": "#C98A1E",
  "Highly Irregular": colors.status.error,
  Unknown: colors.text.tertiary,
};

// ----------------------------- component -----------------------------
export function PredictionPanel({ prediction }: { prediction: Prediction | null }) {
  if (!prediction) return null;

  const p = prediction;
  const hasPrediction = !!p.predictedDate;

  if (!hasPrediction) {
    return (
      <Card style={styles.card} testID="prediction-empty">
        <View style={styles.header}>
          <Ionicons name="pulse-outline" size={16} color={colors.brand.primary} />
          <Text style={styles.headerTitle}>Period prediction</Text>
        </View>
        <Text style={styles.emptyText} testID="prediction-empty-text">
          Log your first period to unlock medical-grade predictions — a forecast window,
          daily probability curve, and personalized trends.
        </Text>
      </Card>
    );
  }

  const cColor = confidenceColor(p.confidence);
  const regColor = REGULARITY_COLOR[p.regularity] ?? colors.text.tertiary;

  return (
    <View testID="prediction-panel">
      {/* ---------- Forecast window + confidence ---------- */}
      <Card style={styles.card} highlight testID="prediction-window-card">
        <View style={styles.header}>
          <Ionicons name="pulse-outline" size={16} color={colors.brand.primary} />
          <Text style={styles.headerTitle}>Next period</Text>
          <View style={[styles.regChip, { backgroundColor: regColor + "22" }]} testID="prediction-regularity-chip">
            <Text style={[styles.regChipText, { color: regColor }]}>{p.regularity}</Text>
          </View>
        </View>

        <Text style={styles.predDate} testID="prediction-date">
          {fmtDate(p.predictedDate)}
        </Text>
        <Text style={styles.windowText} testID="prediction-window">
          Likely window {fmtDate(p.earliestDate)} – {fmtDate(p.latestDate)}
        </Text>

        {/* Confidence band */}
        <View style={styles.confRow}>
          <Text style={styles.confLabel}>Confidence</Text>
          <Text style={[styles.confValue, { color: cColor }]} testID="prediction-confidence">
            {Math.round(p.confidence)}%
          </Text>
        </View>
        <View style={styles.confTrack} testID="prediction-confidence-bar">
          <View style={[styles.confFill, { width: `${p.confidence}%`, backgroundColor: cColor }]} />
        </View>

        <View style={styles.metaRow}>
          <Text style={styles.metaText}>
            Cycle length ~{p.cycleLengthPrediction}d
          </Text>
          <Text style={styles.metaDot}>·</Text>
          <Text style={styles.metaText}>{p.profile.cycle_count} cycles tracked</Text>
        </View>

        {/* Cold-start / data-sufficiency note */}
        {p.dataSufficiency && p.dataSufficiency.level < 4 ? (
          <View style={styles.suffNote} testID="prediction-data-sufficiency">
            <Ionicons name="hourglass-outline" size={13} color={colors.text.tertiary} />
            <Text style={styles.suffNoteText}>
              {p.dataSufficiency.label} — confidence grows as you log more cycles
              (capped at {p.dataSufficiency.max_confidence}% for now).
            </Text>
          </View>
        ) : null}
      </Card>

      {/* ---------- Reliability index ---------- */}
      {p.reliabilityIndex ? (
        <Card style={styles.card} testID="prediction-reliability-card">
          <View style={styles.header}>
            <Ionicons name="shield-checkmark-outline" size={16} color={colors.brand.primary} />
            <Text style={styles.headerTitle}>Reliability index</Text>
          </View>
          <ReliabilityRing
            score={p.reliabilityIndex.score}
            classification={p.reliabilityIndex.classification}
          />
          <Text style={styles.curveHint}>
            How dependable your predictions are — based on cycle count, regularity,
            past accuracy and data completeness.
          </Text>
        </Card>
      ) : null}

      {/* ---------- Prediction range (intervals) ---------- */}
      {p.predictionIntervals && p.predictionIntervals.p95 ? (
        <Card style={styles.card} testID="prediction-intervals-card">
          <Text style={styles.sectionLabel}>Prediction range</Text>
          <IntervalBands intervals={p.predictionIntervals} accent={cColor} />
          <Text style={styles.curveHint}>
            Wider bands capture more certainty. There&apos;s a 95% chance your period
            starts within the outermost range.
          </Text>
        </Card>
      ) : null}

      {/* ---------- Probability curve ---------- */}
      {p.probabilityDistribution.length > 0 ? (
        <Card style={styles.card} testID="prediction-prob-card">
          <Text style={styles.sectionLabel}>Daily probability</Text>
          <ProbabilityCurve points={p.probabilityDistribution} accent={cColor} />
          <Text style={styles.curveHint}>
            Chance your period starts on each day around the forecast.
          </Text>
        </Card>
      ) : null}

      {/* ---------- Fertile window ---------- */}
      {p.fertileWindowStart && p.fertileWindowEnd ? (
        <Card style={styles.card} testID="prediction-fertile-card">
          <View style={styles.header}>
            <Ionicons name="leaf-outline" size={16} color={colors.status.fertile} />
            <Text style={styles.headerTitle}>Fertile window</Text>
          </View>
          <Text style={styles.fertileRange} testID="prediction-fertile-range">
            {fmtDate(p.fertileWindowStart)} – {fmtDate(p.fertileWindowEnd)}
          </Text>
          <FertileBar
            start={p.fertileWindowStart}
            end={p.fertileWindowEnd}
            ovulation={p.ovulationDate}
          />
          {p.ovulationDate ? (
            <Text style={styles.ovuText} testID="prediction-ovulation">
              Estimated ovulation {fmtDate(p.ovulationDate)}
            </Text>
          ) : null}
          <Text style={styles.curveHint}>
            Days you&apos;re most likely to conceive — an estimate, not contraception.
          </Text>
        </Card>
      ) : null}

      {/* ---------- Trend insights ---------- */}
      {p.trendInsights.length > 0 ? (
        <Card style={styles.card} testID="prediction-trends-card">
          <Text style={styles.sectionLabel}>Trends</Text>
          <View style={{ marginTop: spacing.sm }}>
            {p.trendInsights.map((t, i) => (
              <View key={i} style={styles.trendRow} testID={`prediction-trend-${i}`}>
                <Ionicons
                  name={
                    t.direction === "increasing"
                      ? "trending-up-outline"
                      : t.direction === "decreasing"
                        ? "trending-down-outline"
                        : "remove-outline"
                  }
                  size={18}
                  color={colors.brand.primary}
                  style={{ marginTop: 1 }}
                />
                <Text style={styles.trendText}>{t.message}</Text>
              </View>
            ))}
          </View>
        </Card>
      ) : null}

      {/* ---------- Health flags ---------- */}
      {p.healthFlags.length > 0 ? (
        <Card style={styles.card} testID="prediction-flags-card">
          <View style={styles.header}>
            <Ionicons name="information-circle-outline" size={16} color={colors.brand.primary} />
            <Text style={styles.headerTitle}>Things to note</Text>
          </View>
          <View style={{ marginTop: spacing.xs }}>
            {p.healthFlags.map((f, i) => {
              const warn = f.severity === "warning";
              const tint = warn ? colors.status.error : colors.brand.primary;
              return (
                <View key={i} style={styles.flagRow} testID={`prediction-flag-${f.code}`}>
                  <View style={[styles.flagDot, { backgroundColor: tint }]} />
                  <Text style={styles.flagText}>{f.message}</Text>
                </View>
              );
            })}
          </View>
          <Text style={styles.flagDisclaimer}>
            Informational only — not a diagnosis. Consult a clinician with concerns.
          </Text>
        </Card>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { marginHorizontal: spacing.screen, marginTop: spacing.md },
  header: { flexDirection: "row", alignItems: "center", marginBottom: spacing.sm },
  headerTitle: { ...type.h3, color: colors.text.primary, marginLeft: spacing.sm, flex: 1 },
  emptyText: { ...type.bodySm, color: colors.text.secondary, lineHeight: 19, marginTop: spacing.xs },

  regChip: { borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 4 },
  regChipText: { ...type.caption, fontWeight: "700", textTransform: "none" },

  predDate: { fontSize: 36, lineHeight: 42, fontWeight: "700", color: colors.text.primary, letterSpacing: -0.5 },
  windowText: { ...type.bodySm, color: colors.text.secondary, marginTop: 2 },

  confRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-end", marginTop: spacing.md },
  confLabel: { ...type.caption, color: colors.text.tertiary },
  confValue: { ...type.h3, fontWeight: "700" },
  confTrack: { height: 8, borderRadius: 4, backgroundColor: colors.bg.tertiary, marginTop: 6, overflow: "hidden" },
  confFill: { height: 8, borderRadius: 4 },

  metaRow: { flexDirection: "row", alignItems: "center", marginTop: spacing.md },
  metaText: { ...type.bodySm, color: colors.text.tertiary },
  metaDot: { ...type.bodySm, color: colors.text.tertiary, marginHorizontal: 6 },

  suffNote: { flexDirection: "row", alignItems: "flex-start", gap: 6, marginTop: spacing.md },
  suffNoteText: { ...type.caption, color: colors.text.tertiary, flex: 1, lineHeight: 16, textTransform: "none" },

  sectionLabel: { ...type.caption, color: colors.text.tertiary },
  curveHint: { ...type.caption, color: colors.text.tertiary, marginTop: spacing.sm, textTransform: "none" },

  fertileRange: { ...type.h3, color: colors.text.primary, marginBottom: spacing.sm },
  ovuText: { ...type.bodySm, color: colors.status.fertile, fontWeight: "600", marginTop: spacing.sm },

  trendRow: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm, marginTop: spacing.sm },
  trendText: { ...type.bodySm, color: colors.text.primary, flex: 1, lineHeight: 19 },

  flagRow: { flexDirection: "row", alignItems: "flex-start", marginTop: spacing.sm },
  flagDot: { width: 6, height: 6, borderRadius: 3, marginTop: 7, marginRight: spacing.sm },
  flagText: { ...type.bodySm, color: colors.text.primary, flex: 1, lineHeight: 19 },
  flagDisclaimer: { ...type.caption, color: colors.text.tertiary, marginTop: spacing.md, textTransform: "none", lineHeight: 16 },
});
