// Shared types, constants, date helpers, presentational atoms and the StyleSheet
// for the Partner View screen. Extracted from app/partner-view.tsx so the screen
// and its section components (./sections) can stay small and focused.
import { Ionicons } from "@expo/vector-icons";
import { Platform, StyleSheet, Text, View } from "react-native";

import { PartnerReminderPrefs } from "@/src/services/partnerReminders";
import { colors, radius, spacing, type } from "@/src/theme";
import { Prediction } from "@/src/utils/cycle";

export type PartnerPrediction = Prediction & {
  fertile_active?: boolean | null;
  period_active?: boolean | null;
  confidence?: number | null;
};

export type CalendarData = {
  period_days: string[];
  predicted_period_days: string[];
  fertile_days: string[];
  ovulation_day: string | null;
  note_days: string[];
  symptom_days: string[];
};

export type TimelineItem = {
  id: string;
  event_type: string;
  date: string;
  timestamp: string;
  summary: string;
};

export type ViewData = {
  owner_name: string;
  flags: Record<string, boolean>;
  prediction: PartnerPrediction | null;
  last_updated: string | null;
  calendar: CalendarData | null;
  care_suggestions: { icon: string; text: string }[];
  cycle_awareness: {
    cycle_day: number;
    phase: string;
    phase_title: string;
    description: string;
    period_window: string | null;
  } | null;
  symptom_trends: { lines: string[]; cycles_tracked: number } | null;
  weekly_summary: {
    cycle_day?: number;
    water_avg_pct?: number;
    medication_entries?: number;
    symptoms_logged?: number;
    mood_trend?: string;
  } | null;
  emergency_contact: boolean;
  alerts: { id: string; from_name: string; message: string; created_at: string }[];
  logs: {
    date: string;
    symptoms?: { name: string; severity: string }[];
    moods?: string[];
    note?: string;
    tags?: string[];
  }[];
  hydration: { total_ml: number; goal_ml: number; percentage: number } | null;
  meals: { completed_count: number } | null;
  medications: { count: number; items: { name: string; dosage: string; time: string }[] } | null;
  intimacy: { count: number; last_date: string | null } | null;
  timeline: TimelineItem[] | null;
  digest: { headline: string; lines: string[]; week_start: string; week_end: string } | null;
};

export const TIMELINE_ICON: Record<string, string> = {
  water: "water",
  meal: "restaurant",
  medication: "medkit",
  sexual_activity: "heart",
  symptom: "pulse",
  mood: "happy",
};
export const TIMELINE_COLOR: Record<string, string> = {
  water: "#5C9EAD",
  meal: "#E0A458",
  medication: "#A07BD0",
  sexual_activity: "#E8736F",
  symptom: "#D9534F",
  mood: "#2A7A78",
};

export const PERMISSION_META: { key: string; label: string }[] = [
  { key: "periods", label: "Cycle & periods" },
  { key: "fertility", label: "Fertility window" },
  { key: "symptoms", label: "Symptoms" },
  { key: "moods", label: "Moods" },
  { key: "notes", label: "Journal notes" },
  { key: "hydration", label: "Hydration" },
  { key: "meals", label: "Meals" },
  { key: "medications", label: "Medications" },
  { key: "activity", label: "Intimacy" },
  { key: "timeline", label: "Activity timeline" },
  { key: "digest", label: "Weekly digest" },
];

export type RangeKey = "today" | "week" | "month";
export const RANGES: { key: RangeKey; label: string; days: number }[] = [
  { key: "today", label: "Today", days: 0 },
  { key: "week", label: "Week", days: 6 },
  { key: "month", label: "Month", days: 29 },
];

export const REMINDER_META: { key: keyof PartnerReminderPrefs; label: string; sub: string; icon: string }[] = [
  { key: "period", label: "Period approaching", sub: "A heads-up before the next period", icon: "calendar-outline" },
  { key: "hydration", label: "Hydration check-in", sub: "Evening nudge if the goal isn't met", icon: "water-outline" },
  { key: "medication", label: "Medication check-in", sub: "Morning reminder to check in", icon: "medkit-outline" },
];

export const WEEKDAYS = ["S", "M", "T", "W", "T", "F", "S"];

// ---- date helpers ----
export function timeAgo(iso?: string | null): string {
  if (!iso) return "recently";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "recently";
  const diff = Date.now() - d.getTime();
  const m = Math.round(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} hr ago`;
  const days = Math.round(h / 24);
  return `${days} day${days > 1 ? "s" : ""} ago`;
}

export function formatTime(iso?: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

export function isoOf(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate(),
  ).padStart(2, "0")}`;
}

export function shiftISO(iso: string, days: number): string {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + days);
  return isoOf(d);
}

export function monthMatrix(year: number, month: number): (Date | null)[] {
  const first = new Date(year, month, 1);
  const startDow = first.getDay();
  const daysIn = new Date(year, month + 1, 0).getDate();
  const cells: (Date | null)[] = [];
  for (let i = 0; i < startDow; i++) cells.push(null);
  for (let d = 1; d <= daysIn; d++) cells.push(new Date(year, month, d));
  while (cells.length % 7 !== 0) cells.push(null);
  return cells;
}

// ---- presentational atoms ----
export function OverviewStat({ label, value, icon }: { label: string; value: string; icon: string }) {
  return (
    <View style={styles.ovStat}>
      <View style={styles.ovIcon}>
        <Ionicons name={icon as any} size={16} color={colors.brand.primary} />
      </View>
      <Text style={styles.ovValue}>{value}</Text>
      <Text style={styles.ovLabel}>{label}</Text>
    </View>
  );
}

export function Legend({ color, label, dot }: { color: string; label: string; dot?: boolean }) {
  return (
    <View style={styles.legendItem}>
      <View style={[dot ? styles.legendDot : styles.legendSwatch, { backgroundColor: color }]} />
      <Text style={styles.legendText}>{label}</Text>
    </View>
  );
}

export function SummaryStat({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.summaryStat}>
      <Text style={styles.summaryValue}>{value}</Text>
      <Text style={styles.summaryLabel}>{label}</Text>
    </View>
  );
}

export const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg.primary },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingBottom: spacing.md },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center", marginRight: spacing.xs },
  headerTitle: { ...type.h2, color: colors.text.primary },
  readonlyBadge: { flexDirection: "row", alignItems: "center", marginTop: 2 },
  readonlyText: { ...type.bodySm, color: colors.brand.primary, marginLeft: 4, fontWeight: "600" },
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl },
  errorText: { ...type.body, color: colors.text.secondary, textAlign: "center", marginTop: spacing.md },
  card: { marginBottom: spacing.md },
  sectionLabel: { ...type.caption, color: colors.text.tertiary, marginBottom: spacing.sm },
  helpText: { ...type.bodySm, color: colors.text.secondary, marginBottom: spacing.sm },

  // overview
  overviewCard: {
    marginBottom: spacing.md,
    backgroundColor: colors.brand.indigo,
  },
  overviewEyebrow: {
    ...type.caption,
    color: "rgba(255,255,255,0.7)",
    marginBottom: spacing.md,
  },
  overviewGrid: { flexDirection: "row", gap: spacing.md },
  ovStat: {
    flex: 1,
    backgroundColor: "rgba(255,255,255,0.08)",
    borderRadius: radius.md,
    padding: spacing.md,
  },
  ovIcon: {
    width: 30,
    height: 30,
    borderRadius: 15,
    backgroundColor: "rgba(255,255,255,0.15)",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.sm,
  },
  ovValue: { ...type.h3, color: "#fff" },
  ovLabel: { ...type.bodySm, color: "rgba(255,255,255,0.7)", marginTop: 2 },
  fertilePill: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "flex-start",
    paddingVertical: 6,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    marginTop: spacing.md,
  },
  fertileText: { ...type.bodySm, fontWeight: "700", marginLeft: 6 },

  // care
  careRow: { flexDirection: "row", alignItems: "flex-start", marginBottom: spacing.sm },
  careIcon: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.brand.primaryLight,
    alignItems: "center",
    justifyContent: "center",
    marginRight: spacing.sm,
  },
  careText: { ...type.body, color: colors.text.primary, flex: 1, lineHeight: 21 },
  careDisclaimer: { ...type.bodySm, color: colors.text.tertiary, marginTop: 2, fontStyle: "italic" },

  // digest
  digestCard: {
    marginBottom: spacing.md,
    backgroundColor: colors.brand.primaryLight,
    borderLeftWidth: 3,
    borderLeftColor: colors.brand.primary,
  },
  digestHeader: { flexDirection: "row", alignItems: "center", marginBottom: spacing.xs },
  digestEyebrow: {
    ...type.caption,
    color: colors.brand.primary,
    fontWeight: "700",
    marginLeft: spacing.xs,
  },
  digestHeadline: { ...type.h3, color: colors.text.primary, lineHeight: 24, marginBottom: spacing.sm },
  digestRow: { flexDirection: "row", alignItems: "flex-start", marginTop: 6 },
  digestDot: { width: 5, height: 5, borderRadius: 3, backgroundColor: colors.brand.primary, marginTop: 7, marginRight: spacing.sm },
  digestLine: { ...type.bodySm, color: colors.text.secondary, flex: 1, lineHeight: 19 },

  // calendar
  calHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.sm },
  calNav: { flexDirection: "row", alignItems: "center" },
  calNavBtn: { padding: 4 },
  calMonthLabel: { ...type.bodySm, color: colors.text.primary, fontWeight: "600", minWidth: 120, textAlign: "center" },
  weekRow: { flexDirection: "row", marginBottom: 4 },
  weekday: { flex: 1, textAlign: "center", ...type.bodySm, color: colors.text.tertiary, fontWeight: "600" },
  calGrid: { flexDirection: "row", flexWrap: "wrap" },
  calCell: { width: `${100 / 7}%`, alignItems: "center", paddingVertical: 3 },
  dayCircle: { width: 32, height: 32, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  dayToday: { borderWidth: 1.5, borderColor: colors.brand.primary },
  dayText: { ...type.bodySm, fontWeight: "600" },
  dotRow: { flexDirection: "row", height: 6, marginTop: 2, gap: 2 },
  calDot: { width: 4, height: 4, borderRadius: 2 },
  legendRow: { flexDirection: "row", flexWrap: "wrap", marginTop: spacing.md, gap: spacing.md },
  legendItem: { flexDirection: "row", alignItems: "center" },
  legendSwatch: { width: 12, height: 12, borderRadius: 3, marginRight: 5 },
  legendDot: { width: 7, height: 7, borderRadius: 4, marginRight: 5 },
  legendText: { ...type.bodySm, color: colors.text.secondary },

  // today / stats
  statTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: spacing.sm },
  statLabelRow: { flexDirection: "row", alignItems: "center" },
  statLabel: { ...type.body, color: colors.text.secondary, marginLeft: spacing.sm, fontWeight: "600" },
  statValue: { ...type.bodySm, color: colors.text.primary, fontWeight: "700" },
  progressTrack: { height: 8, borderRadius: 4, backgroundColor: colors.bg.tertiary, marginTop: spacing.xs, overflow: "hidden" },
  progressFill: { height: 8, borderRadius: 4, backgroundColor: "#5C9EAD" },
  medRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: spacing.sm },
  medName: { ...type.body, color: colors.text.primary, flex: 1 },
  takenChip: { flexDirection: "row", alignItems: "center", backgroundColor: "#EAF5EF", paddingVertical: 3, paddingHorizontal: 8, borderRadius: radius.pill },
  takenText: { ...type.bodySm, color: colors.status.success, fontWeight: "600", marginLeft: 4 },
  medEmpty: { ...type.bodySm, color: colors.text.tertiary, marginTop: 4 },

  // segment
  segment: { flexDirection: "row", backgroundColor: colors.bg.secondary, borderRadius: radius.md, padding: 3, marginBottom: spacing.md },
  segBtn: { flex: 1, paddingVertical: 7, alignItems: "center", borderRadius: radius.sm },
  segBtnActive: {
    backgroundColor: "#fff",
    elevation: 1,
    ...Platform.select({
      web: { boxShadow: "0px 1px 3px rgba(0,0,0,0.06)" },
      default: { shadowColor: "#000", shadowOpacity: 0.06, shadowRadius: 3, shadowOffset: { width: 0, height: 1 } },
    }),
  },
  segText: { ...type.bodySm, color: colors.text.secondary, fontWeight: "600" },
  segTextActive: { color: colors.brand.primary },

  // timeline
  tlRow: { flexDirection: "row", alignItems: "center", paddingVertical: spacing.sm },
  tlIcon: { width: 32, height: 32, borderRadius: 16, alignItems: "center", justifyContent: "center", marginRight: spacing.md },
  tlSummary: { ...type.body, color: colors.text.primary, fontWeight: "600" },
  tlDate: { ...type.bodySm, color: colors.text.tertiary, marginTop: 1 },

  // reminders
  reminderRow: { flexDirection: "row", alignItems: "center", paddingVertical: spacing.sm },
  reminderIcon: { width: 32, height: 32, borderRadius: 16, backgroundColor: colors.brand.primaryLight, alignItems: "center", justifyContent: "center", marginRight: spacing.md },
  reminderLabel: { ...type.body, color: colors.text.primary, fontWeight: "600" },
  reminderSub: { ...type.bodySm, color: colors.text.tertiary, marginTop: 1 },
  reminderNote: { ...type.bodySm, color: colors.text.tertiary, marginTop: spacing.sm, fontStyle: "italic" },

  // permissions
  permRow: { flexDirection: "row", alignItems: "center", paddingVertical: 6 },
  permLabel: { ...type.body, color: colors.text.primary, marginLeft: spacing.sm },

  // logs
  logDate: { ...type.body, color: colors.text.primary, fontWeight: "600", marginBottom: 4 },
  logText: { ...type.bodySm, color: colors.text.secondary, marginTop: 2 },
  empty: { ...type.body, color: colors.text.tertiary },
  disclaimer: { ...type.bodySm, color: colors.text.tertiary, textAlign: "center", marginTop: spacing.lg },

  // shared-space CTA
  spaceCta: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.brand.primaryLight,
    borderRadius: radius.lg,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  spaceCtaIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.brand.primary,
    alignItems: "center",
    justifyContent: "center",
    marginRight: spacing.md,
  },
  spaceCtaTitle: { ...type.body, color: colors.text.primary, fontWeight: "700" },
  spaceCtaSub: { ...type.bodySm, color: colors.text.secondary, marginTop: 1 },

  // cycle awareness
  awarenessHead: { flexDirection: "row", alignItems: "center", marginBottom: spacing.sm },
  awarenessDay: {
    width: 54,
    height: 54,
    borderRadius: 27,
    backgroundColor: colors.brand.indigoLight,
    alignItems: "center",
    justifyContent: "center",
    marginRight: spacing.md,
  },
  awarenessDayNum: { ...type.h3, color: colors.brand.indigo },
  awarenessDayLbl: { ...type.bodySm, color: colors.text.tertiary, marginTop: -2 },
  awarenessPhase: { ...type.body, color: colors.text.primary, fontWeight: "700" },
  awarenessWindow: { ...type.bodySm, color: colors.status.periodActive, fontWeight: "600", marginTop: 2 },
  awarenessDesc: { ...type.bodySm, color: colors.text.secondary, lineHeight: 20 },

  // confidence
  overviewPredict: {
    ...type.bodySm,
    color: "rgba(255,255,255,0.85)",
    fontWeight: "600",
    marginTop: spacing.md,
  },

  // emergency
  emergencyCard: {
    backgroundColor: "#C0453E",
    borderRadius: radius.lg,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  emergencyHead: { flexDirection: "row", alignItems: "center", marginBottom: 4 },
  emergencyTitle: { ...type.body, color: "#fff", fontWeight: "800", marginLeft: 6 },
  emergencySub: { ...type.bodySm, color: "rgba(255,255,255,0.9)" },
  alertRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    backgroundColor: "rgba(255,255,255,0.15)",
    borderRadius: radius.sm,
    padding: spacing.sm,
    marginTop: spacing.sm,
  },
  alertText: { ...type.bodySm, color: "#fff", fontWeight: "600", marginLeft: 6, flex: 1 },

  // weekly summary
  summaryGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  summaryStat: {
    width: "31%",
    backgroundColor: colors.bg.secondary,
    borderRadius: radius.md,
    paddingVertical: spacing.md,
    alignItems: "center",
  },
  summaryValue: { ...type.h3, color: colors.brand.primary },
  summaryLabel: { ...type.bodySm, color: colors.text.tertiary, marginTop: 2, textAlign: "center" },
});
