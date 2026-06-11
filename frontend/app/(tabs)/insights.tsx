import { Ionicons } from "@expo/vector-icons";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Svg, { Rect } from "react-native-svg";

import { api } from "@/src/api/client";
import { PredictionPanel, type Prediction } from "@/src/components/PredictionPanel";
import { AccuracyTrail, type PredictionHistory } from "@/src/components/prediction/AccuracyTrail";
import { Card } from "@/src/components/ui";
import { PREDICTION_DISCLAIMER } from "@/src/constants";
import { useFetch } from "@/src/hooks/useFetch";
import { colors, radius, spacing, type } from "@/src/theme";

type Analytics = {
  avg_cycle_length: number | null;
  avg_period_length: number | null;
  regularity_score: number | null;
  cycles_tracked: number;
  cycle_lengths: number[];
  symptom_frequency: { name: string; count: number }[];
  mood_frequency: { name: string; count: number }[];
};

type Phase = "menstrual" | "follicular" | "ovulation" | "luteal";
type SymptomPattern = {
  name: string;
  total_count: number;
  by_phase: Record<Phase, number>;
  dominant_phase: Phase;
  dominant_phase_pct: number;
  peak_day_range: string | null;
  peak_day_pct: number;
  premenstrual_cycle_rate: number;
  cycle_recurrence_rate: number;
  typical_days_before: number | null;
  insight: string;
  confident: boolean;
};
type Patterns = {
  has_enough_data: boolean;
  cycles_tracked: number;
  total_symptom_logs: number;
  symptoms: SymptomPattern[];
  insights: string[];
};

const PHASE_ORDER: Phase[] = ["menstrual", "follicular", "ovulation", "luteal"];
const PHASE_COLOR: Record<Phase, string> = {
  menstrual: "#D9534F",
  follicular: "#5C9EAD",
  ovulation: "#5FC79B",
  luteal: "#A07BD0",
};
const PHASE_LABEL: Record<Phase, string> = {
  menstrual: "Menstrual",
  follicular: "Follicular",
  ovulation: "Ovulation",
  luteal: "Luteal",
};

export default function Insights() {
  const insets = useSafeAreaInsets();

  const { data: combined } = useFetch(
    async () => {
      const [a, p, pred, hist] = await Promise.all([
        api.get<Analytics>("/analytics"),
        api.get<Patterns>("/symptom-patterns").catch(() => null),
        api.get<Prediction>("/prediction").catch(() => null),
        api.get<PredictionHistory>("/prediction/history?limit=24").catch(() => null),
      ]);
      return { analytics: a, patterns: p, prediction: pred, history: hist };
    },
    { refetchOnFocus: true },
  );
  const data = combined?.analytics ?? null;
  const patterns = combined?.patterns ?? null;
  const prediction = combined?.prediction ?? null;
  const history = combined?.history ?? null;

  const maxSymptom = Math.max(1, ...(data?.symptom_frequency.map((s) => s.count) || [1]));

  return (
    <ScrollView
      testID="insights-screen"
      style={styles.screen}
      contentContainerStyle={{ paddingBottom: spacing.xxl, paddingTop: insets.top + spacing.md }}
    >
      <Text style={styles.title}>Insights</Text>

      <PredictionPanel prediction={prediction} />

      {prediction?.predictedDate ? <AccuracyTrail data={history} /> : null}

      <View style={styles.row}>
        <StatCard
          testID="insight-avg-cycle"
          value={data?.avg_cycle_length ? `${data.avg_cycle_length}` : "—"}
          unit="days"
          label="Avg cycle"
        />
        <StatCard
          testID="insight-avg-period"
          value={data?.avg_period_length ? `${data.avg_period_length}` : "—"}
          unit="days"
          label="Avg period"
        />
      </View>

      <Card style={styles.regCard} testID="insight-regularity">
        <Text style={styles.sectionLabel}>Regularity score</Text>
        <View style={styles.regRow}>
          <Text style={styles.regValue}>
            {data?.regularity_score != null ? data.regularity_score : "—"}
            {data?.regularity_score != null ? (
              <Text style={styles.regOf}> / 100</Text>
            ) : null}
          </Text>
        </View>
        <View style={styles.regBarTrack}>
          <View
            style={[
              styles.regBarFill,
              { width: `${data?.regularity_score ?? 0}%` },
            ]}
          />
        </View>
        <Text style={styles.regHint}>
          {data?.cycles_tracked
            ? `Based on ${data.cycles_tracked} tracked cycle${data.cycles_tracked > 1 ? "s" : ""}`
            : "Log more cycles to compute regularity"}
        </Text>
      </Card>

      <Card style={styles.regCard} testID="insight-patterns">
        <View style={styles.patHeader}>
          <Ionicons name="sparkles-outline" size={16} color={colors.brand.primary} />
          <Text style={styles.patTitle}>Symptom patterns</Text>
        </View>
        {patterns?.has_enough_data ? (
          <View>
            {patterns.insights.length ? (
              <View style={styles.insightList}>
                {patterns.insights.map((t, i) => (
                  <View key={i} style={styles.insightRow} testID={`pattern-insight-${i}`}>
                    <View style={styles.insightDot} />
                    <Text style={styles.insightText}>{t}</Text>
                  </View>
                ))}
              </View>
            ) : (
              <Text style={styles.empty}>Keep logging to surface clearer patterns.</Text>
            )}

            <View style={styles.legendRow}>
              {PHASE_ORDER.map((ph) => (
                <View key={ph} style={styles.legendItem}>
                  <View style={[styles.legendDot, { backgroundColor: PHASE_COLOR[ph] }]} />
                  <Text style={styles.legendText}>{PHASE_LABEL[ph]}</Text>
                </View>
              ))}
            </View>

            {patterns.symptoms.map((s) => (
              <PatternRow key={s.name} pattern={s} />
            ))}
          </View>
        ) : (
          <Text style={styles.patEmpty} testID="pattern-empty">
            Track at least 2 cycles and log a few symptoms to unlock personalized patterns
            {patterns
              ? ` (${patterns.total_symptom_logs} symptom${
                  patterns.total_symptom_logs === 1 ? "" : "s"
                } logged so far).`
              : "."}
          </Text>
        )}
      </Card>

      <Card style={styles.chartCard} testID="insight-symptom-chart">
        <Text style={styles.sectionLabel}>Symptom frequency</Text>
        {data?.symptom_frequency.length ? (
          <View style={{ marginTop: spacing.sm }}>
            {data.symptom_frequency.map((s) => (
              <View key={s.name} style={styles.barRow}>
                <Text style={styles.barLabel} numberOfLines={1}>
                  {s.name}
                </Text>
                <View style={styles.barTrack}>
                  <Svg height={16} width="100%">
                    <Rect x={0} y={2} width="100%" height={12} rx={6} fill={colors.bg.tertiary} />
                    <Rect
                      x={0}
                      y={2}
                      width={`${(s.count / maxSymptom) * 100}%`}
                      height={12}
                      rx={6}
                      fill={colors.brand.primary}
                    />
                  </Svg>
                </View>
                <Text style={styles.barCount}>{s.count}</Text>
              </View>
            ))}
          </View>
        ) : (
          <Text style={styles.empty}>No symptoms logged yet.</Text>
        )}
      </Card>

      <Card style={styles.chartCard} testID="insight-mood-chart">
        <Text style={styles.sectionLabel}>Top moods</Text>
        {data?.mood_frequency.length ? (
          <View style={styles.moodWrap}>
            {data.mood_frequency.map((m) => (
              <View key={m.name} style={styles.moodPill}>
                <Text style={styles.moodName}>{m.name}</Text>
                <Text style={styles.moodCount}>{m.count}</Text>
              </View>
            ))}
          </View>
        ) : (
          <Text style={styles.empty}>No moods logged yet.</Text>
        )}
      </Card>

      <Text style={styles.disclaimer}>{PREDICTION_DISCLAIMER}</Text>
    </ScrollView>
  );
}

function StatCard({
  value,
  unit,
  label,
  testID,
}: {
  value: string;
  unit: string;
  label: string;
  testID?: string;
}) {
  return (
    <Card style={styles.statCard} testID={testID}>
      <Text style={styles.statValue}>
        {value}
        <Text style={styles.statUnit}> {unit}</Text>
      </Text>
      <Text style={styles.statLabel}>{label}</Text>
    </Card>
  );
}

function PatternRow({ pattern }: { pattern: SymptomPattern }) {
  return (
    <View style={styles.patRow} testID={`pattern-${pattern.name}`}>
      <View style={styles.patRowTop}>
        <Text style={styles.patName} numberOfLines={1}>
          {pattern.name}
        </Text>
        <Text style={styles.patMeta}>
          {PHASE_LABEL[pattern.dominant_phase]} · {pattern.dominant_phase_pct}%
        </Text>
      </View>
      <View style={styles.phaseBar}>
        {PHASE_ORDER.map((ph) => {
          const c = pattern.by_phase[ph] || 0;
          if (c <= 0) return null;
          return (
            <View key={ph} style={{ flex: c, backgroundColor: PHASE_COLOR[ph] }} />
          );
        })}
      </View>
      {pattern.typical_days_before != null && pattern.premenstrual_cycle_rate >= 50 ? (
        <View style={styles.leadBadge} testID={`pattern-lead-${pattern.name}`}>
          <Ionicons name="alert-circle-outline" size={13} color="#B05B25" />
          <Text style={styles.leadText}>
            {pattern.typical_days_before === 0
              ? "Often on the day your period starts"
              : `Often ~${pattern.typical_days_before}d before your period`}
            {" · "}
            {pattern.premenstrual_cycle_rate}% of cycles
          </Text>
        </View>
      ) : null}
      {pattern.peak_day_range ? (
        <Text style={styles.patHint}>
          Peaks on cycle days {pattern.peak_day_range} · seen in {pattern.cycle_recurrence_rate}% of cycles
        </Text>
      ) : (
        <Text style={styles.patHint}>Seen in {pattern.cycle_recurrence_rate}% of tracked cycles</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg.primary },
  title: { ...type.h1, color: colors.text.primary, paddingHorizontal: spacing.screen, marginBottom: spacing.md },
  row: { flexDirection: "row", paddingHorizontal: spacing.screen, gap: spacing.sm },
  statCard: { flex: 1, padding: spacing.lg },
  statValue: { ...type.h1, color: colors.text.primary },
  statUnit: { ...type.body, color: colors.text.tertiary },
  statLabel: { ...type.bodySm, color: colors.text.secondary, marginTop: 2 },
  regCard: { marginHorizontal: spacing.screen, marginTop: spacing.md },
  sectionLabel: { ...type.caption, color: colors.text.tertiary },
  regRow: { marginTop: spacing.sm },
  regValue: { fontSize: 40, fontWeight: "700", color: colors.brand.primary },
  regOf: { ...type.body, color: colors.text.tertiary, fontWeight: "400" },
  regBarTrack: { height: 8, borderRadius: 4, backgroundColor: colors.bg.tertiary, marginTop: spacing.sm, overflow: "hidden" },
  regBarFill: { height: 8, borderRadius: 4, backgroundColor: colors.brand.primary },
  regHint: { ...type.bodySm, color: colors.text.tertiary, marginTop: spacing.sm },
  chartCard: { marginHorizontal: spacing.screen, marginTop: spacing.md },
  barRow: { flexDirection: "row", alignItems: "center", marginVertical: 5 },
  barLabel: { ...type.bodySm, color: colors.text.secondary, width: 110 },
  barTrack: { flex: 1, marginHorizontal: spacing.sm },
  barCount: { ...type.bodySm, color: colors.text.primary, width: 24, textAlign: "right", fontWeight: "600" },
  moodWrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.sm },
  moodPill: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.brand.primaryLight,
    borderRadius: radius.pill,
    paddingVertical: 6,
    paddingHorizontal: 12,
  },
  moodName: { ...type.bodySm, color: colors.brand.primary, fontWeight: "600" },
  moodCount: { ...type.bodySm, color: colors.brand.primary, marginLeft: 6, fontWeight: "700" },
  empty: { ...type.body, color: colors.text.tertiary, marginTop: spacing.sm },
  patHeader: { flexDirection: "row", alignItems: "center", marginBottom: spacing.sm },
  patTitle: { ...type.h3, color: colors.text.primary, marginLeft: spacing.sm },
  insightList: { marginBottom: spacing.md },
  insightRow: { flexDirection: "row", alignItems: "flex-start", marginTop: spacing.sm },
  insightDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.brand.primary,
    marginTop: 7,
    marginRight: spacing.sm,
  },
  insightText: { ...type.bodySm, color: colors.text.primary, flex: 1, lineHeight: 19 },
  legendRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.md,
    marginBottom: spacing.sm,
    marginTop: spacing.xs,
  },
  legendItem: { flexDirection: "row", alignItems: "center" },
  legendDot: { width: 8, height: 8, borderRadius: 4, marginRight: 5 },
  legendText: { ...type.caption, color: colors.text.secondary },
  patRow: { marginTop: spacing.md },
  patRowTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  patName: { ...type.body, color: colors.text.primary, fontWeight: "600", flex: 1, marginRight: spacing.sm },
  patMeta: { ...type.bodySm, color: colors.text.secondary, fontWeight: "600" },
  phaseBar: {
    flexDirection: "row",
    height: 10,
    borderRadius: 5,
    overflow: "hidden",
    backgroundColor: colors.bg.tertiary,
    marginTop: 6,
  },
  patHint: { ...type.caption, color: colors.text.tertiary, marginTop: 4 },
  leadBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    alignSelf: "flex-start",
    backgroundColor: "#FFF3EC",
    borderRadius: radius.pill,
    paddingVertical: 4,
    paddingHorizontal: 8,
    marginTop: 6,
  },
  leadText: { ...type.caption, color: "#B05B25", fontWeight: "700", textTransform: "none" },
  patEmpty: { ...type.bodySm, color: colors.text.secondary, lineHeight: 19 },
  disclaimer: { ...type.bodySm, color: colors.text.tertiary, textAlign: "center", marginTop: spacing.xl, paddingHorizontal: spacing.screen },
});
