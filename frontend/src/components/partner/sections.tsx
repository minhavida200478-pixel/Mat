// Partner View section components. Each renders one card/section of the partner
// dashboard from a minimal prop slice; the screen (app/partner-view.tsx) wires
// them together. Styles/types/helpers/atoms live in ./shared.
import { Ionicons } from "@expo/vector-icons";
import { Platform, Switch, Text, TouchableOpacity, View } from "react-native";

import { Card } from "@/src/components/ui";
import { PartnerReminderPrefs } from "@/src/services/partnerReminders";
import { colors, spacing } from "@/src/theme";
import { formatLong, formatNice, todayISO } from "@/src/utils/cycle";

import {
  CalendarData,
  Legend,
  OverviewStat,
  PERMISSION_META,
  PartnerPrediction,
  RANGES,
  RangeKey,
  REMINDER_META,
  SummaryStat,
  TIMELINE_COLOR,
  TIMELINE_ICON,
  TimelineItem,
  ViewData,
  WEEKDAYS,
  formatTime,
  isoOf,
  monthMatrix,
  styles,
} from "./shared";

export function EmergencyBanner({ data }: { data: ViewData }) {
  if (!data.emergency_contact) return null;
  return (
    <View style={styles.emergencyCard} testID="pv-emergency">
      <View style={styles.emergencyHead}>
        <Ionicons name="alert-circle" size={18} color="#fff" />
        <Text style={styles.emergencyTitle}>Emergency contact</Text>
      </View>
      <Text style={styles.emergencySub}>
        You&apos;re {(data.owner_name || "your partner").split(" ")[0]}&apos;s emergency contact for
        important health alerts.
      </Text>
      {data.alerts.map((a) => (
        <View key={a.id} style={styles.alertRow} testID={`pv-alert-${a.id}`}>
          <Ionicons name="notifications" size={14} color="#fff" />
          <Text style={styles.alertText}>{a.message}</Text>
        </View>
      ))}
    </View>
  );
}

export function SharedSpaceCta({ onPress }: { onPress: () => void }) {
  return (
    <TouchableOpacity testID="pv-open-space" style={styles.spaceCta} activeOpacity={0.85} onPress={onPress}>
      <View style={styles.spaceCtaIcon}>
        <Ionicons name="chatbubbles" size={20} color="#fff" />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.spaceCtaTitle}>Shared space</Text>
        <Text style={styles.spaceCtaSub}>Notes, check-ins & a shared to-do list</Text>
      </View>
      <Ionicons name="chevron-forward" size={20} color={colors.brand.primary} />
    </TouchableOpacity>
  );
}

export function OverviewSection({ p, flags }: { p: PartnerPrediction; flags?: Record<string, boolean> }) {
  if (!p || !p.has_data) return null;
  return (
    <Card style={styles.overviewCard} testID="pv-overview">
      <Text style={styles.overviewEyebrow}>Relationship overview</Text>
      <View style={styles.overviewGrid}>
        {p.cycle_day != null ? (
          <OverviewStat label="Cycle day" value={`Day ${p.cycle_day}`} icon="ellipse-outline" />
        ) : null}
        {p.days_until_next_period != null ? (
          <OverviewStat
            label="Period expected"
            value={
              p.period_active
                ? "Now"
                : p.days_until_next_period > 0
                  ? `${p.days_until_next_period} day${p.days_until_next_period === 1 ? "" : "s"}`
                  : p.days_until_next_period === 0
                    ? "Today"
                    : `${Math.abs(p.days_until_next_period)}d late`
            }
            icon="water-outline"
          />
        ) : null}
      </View>
      {flags?.fertility ? (
        <View
          style={[
            styles.fertilePill,
            { backgroundColor: p.fertile_active ? colors.status.fertileLight : colors.bg.secondary },
          ]}
          testID="pv-fertility-status"
        >
          <Ionicons name="leaf" size={14} color={p.fertile_active ? colors.status.fertile : colors.text.tertiary} />
          <Text
            style={[
              styles.fertileText,
              { color: p.fertile_active ? colors.status.fertile : colors.text.tertiary },
            ]}
          >
            Fertility window: {p.fertile_active ? "Active" : "Inactive"}
          </Text>
        </View>
      ) : null}
      {flags?.periods && p.next_period_date && p.confidence != null ? (
        <Text style={styles.overviewPredict} testID="pv-confidence">
          Next period {formatNice(p.next_period_date)} · {p.confidence}% confidence
        </Text>
      ) : null}
    </Card>
  );
}

export function CareSection({ suggestions }: { suggestions: ViewData["care_suggestions"] }) {
  if (!suggestions?.length) return null;
  return (
    <Card style={styles.card} testID="pv-care">
      <Text style={styles.sectionLabel}>Care suggestions</Text>
      {suggestions.map((s, i) => (
        <View key={i} style={styles.careRow} testID={`pv-care-${i}`}>
          <View style={styles.careIcon}>
            <Ionicons name={(s.icon + "-outline") as any} size={16} color={colors.brand.primary} />
          </View>
          <Text style={styles.careText}>{s.text}</Text>
        </View>
      ))}
      <Text style={styles.careDisclaimer}>Informational only — not medical advice.</Text>
    </Card>
  );
}

export function CycleAwarenessSection({ awareness }: { awareness: ViewData["cycle_awareness"] }) {
  if (!awareness) return null;
  return (
    <Card style={styles.card} testID="pv-awareness">
      <Text style={styles.sectionLabel}>Cycle awareness</Text>
      <View style={styles.awarenessHead}>
        <View style={styles.awarenessDay}>
          <Text style={styles.awarenessDayNum}>{awareness.cycle_day}</Text>
          <Text style={styles.awarenessDayLbl}>day</Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.awarenessPhase}>{awareness.phase_title}</Text>
          {awareness.period_window ? (
            <Text style={styles.awarenessWindow}>{awareness.period_window}</Text>
          ) : null}
        </View>
      </View>
      <Text style={styles.awarenessDesc}>{awareness.description}</Text>
    </Card>
  );
}

export function SymptomTrendsSection({ trends }: { trends: ViewData["symptom_trends"] }) {
  if (!trends?.lines?.length) return null;
  return (
    <Card style={styles.card} testID="pv-trends">
      <Text style={styles.sectionLabel}>Symptom trends</Text>
      {trends.lines.map((line, i) => (
        <View key={i} style={styles.careRow} testID={`pv-trend-${i}`}>
          <View style={styles.careIcon}>
            <Ionicons name="trending-up" size={15} color={colors.brand.primary} />
          </View>
          <Text style={styles.careText}>{line}</Text>
        </View>
      ))}
      <Text style={styles.careDisclaimer}>
        Based on {trends.cycles_tracked} tracked cycles · helps you understand patterns.
      </Text>
    </Card>
  );
}

export function DigestSection({ digest }: { digest: ViewData["digest"] }) {
  if (!digest) return null;
  return (
    <Card style={styles.digestCard} testID="pv-digest">
      <View style={styles.digestHeader}>
        <Ionicons name="newspaper-outline" size={16} color={colors.brand.primary} />
        <Text style={styles.digestEyebrow}>This week</Text>
      </View>
      <Text style={styles.digestHeadline} testID="pv-digest-headline">
        {digest.headline}
      </Text>
      {digest.lines.map((line, i) => (
        <View key={i} style={styles.digestRow} testID={`pv-digest-line-${i}`}>
          <View style={styles.digestDot} />
          <Text style={styles.digestLine}>{line}</Text>
        </View>
      ))}
    </Card>
  );
}

export function WeeklySummarySection({ summary }: { summary: ViewData["weekly_summary"] }) {
  if (!summary) return null;
  return (
    <Card style={styles.card} testID="pv-weekly-summary">
      <Text style={styles.sectionLabel}>Weekly summary</Text>
      <View style={styles.summaryGrid}>
        {summary.cycle_day != null ? <SummaryStat label="Cycle day" value={`${summary.cycle_day}`} /> : null}
        {summary.water_avg_pct != null ? <SummaryStat label="Water avg" value={`${summary.water_avg_pct}%`} /> : null}
        {summary.symptoms_logged != null ? <SummaryStat label="Symptoms" value={`${summary.symptoms_logged}`} /> : null}
        {summary.medication_entries != null ? <SummaryStat label="Medication" value={`${summary.medication_entries}`} /> : null}
        {summary.mood_trend ? <SummaryStat label="Mood" value={summary.mood_trend} /> : null}
      </View>
    </Card>
  );
}

type CalSets = {
  period: Set<string>;
  predicted: Set<string>;
  fertile: Set<string>;
  note: Set<string>;
  symptom: Set<string>;
  ovulation: string | null;
};

export function CalendarSection({
  cal,
  calSets,
  calMonth,
  setCalMonth,
}: {
  cal: CalendarData | null | undefined;
  calSets: CalSets;
  calMonth: Date;
  setCalMonth: (d: Date) => void;
}) {
  if (!cal) return null;
  return (
    <Card style={styles.card} testID="pv-calendar">
      <View style={styles.calHeader}>
        <Text style={styles.sectionLabel}>Shared calendar</Text>
        <View style={styles.calNav}>
          <TouchableOpacity
            testID="pv-cal-prev"
            onPress={() => setCalMonth(new Date(calMonth.getFullYear(), calMonth.getMonth() - 1, 1))}
            style={styles.calNavBtn}
          >
            <Ionicons name="chevron-back" size={18} color={colors.text.secondary} />
          </TouchableOpacity>
          <Text style={styles.calMonthLabel}>
            {calMonth.toLocaleDateString(undefined, { month: "long", year: "numeric" })}
          </Text>
          <TouchableOpacity
            testID="pv-cal-next"
            onPress={() => setCalMonth(new Date(calMonth.getFullYear(), calMonth.getMonth() + 1, 1))}
            style={styles.calNavBtn}
          >
            <Ionicons name="chevron-forward" size={18} color={colors.text.secondary} />
          </TouchableOpacity>
        </View>
      </View>

      <View style={styles.weekRow}>
        {WEEKDAYS.map((w, i) => (
          <Text key={i} style={styles.weekday}>
            {w}
          </Text>
        ))}
      </View>
      <View style={styles.calGrid}>
        {monthMatrix(calMonth.getFullYear(), calMonth.getMonth()).map((d, i) => {
          if (!d) return <View key={i} style={styles.calCell} />;
          const iso = isoOf(d);
          const isPeriod = calSets.period.has(iso);
          const isPredicted = calSets.predicted.has(iso);
          const isOvulation = calSets.ovulation === iso;
          const isFertile = calSets.fertile.has(iso);
          const isToday = iso === todayISO();
          let bg = "transparent";
          let fg = colors.text.primary;
          if (isPeriod) {
            bg = colors.status.periodActive;
            fg = "#fff";
          } else if (isPredicted) {
            bg = colors.status.periodLight;
            fg = colors.status.periodActive;
          } else if (isOvulation) {
            bg = colors.status.fertile;
            fg = "#fff";
          } else if (isFertile) {
            bg = colors.status.fertileLight;
            fg = colors.status.fertile;
          }
          return (
            <View key={i} style={styles.calCell}>
              <View style={[styles.dayCircle, { backgroundColor: bg }, isToday && styles.dayToday]}>
                <Text style={[styles.dayText, { color: fg }]}>{d.getDate()}</Text>
              </View>
              <View style={styles.dotRow}>
                {calSets.symptom.has(iso) ? <View style={[styles.calDot, { backgroundColor: "#E0A458" }]} /> : null}
                {calSets.note.has(iso) ? <View style={[styles.calDot, { backgroundColor: colors.brand.indigo }]} /> : null}
              </View>
            </View>
          );
        })}
      </View>

      <View style={styles.legendRow}>
        <Legend color={colors.status.periodActive} label="Period" />
        <Legend color={colors.status.periodLight} label="Predicted" />
        <Legend color={colors.status.fertileLight} label="Fertile" />
        <Legend color="#E0A458" label="Symptom" dot />
        <Legend color={colors.brand.indigo} label="Note" dot />
      </View>
    </Card>
  );
}

export function TodaySection({
  hydration,
  meals,
  medications,
}: {
  hydration: ViewData["hydration"];
  meals: ViewData["meals"];
  medications: ViewData["medications"];
}) {
  if (!hydration && !meals && !medications) return null;
  return (
    <Card style={styles.card} testID="pv-today">
      <Text style={styles.sectionLabel}>Today</Text>
      {hydration ? (
        <View style={{ marginTop: spacing.xs }}>
          <View style={styles.statTop}>
            <View style={styles.statLabelRow}>
              <Ionicons name="water" size={16} color="#5C9EAD" />
              <Text style={styles.statLabel}>Hydration</Text>
            </View>
            <Text style={styles.statValue}>
              {(hydration.total_ml / 1000).toFixed(1)}L / {(hydration.goal_ml / 1000).toFixed(1)}L ·{" "}
              {Math.round(hydration.percentage)}%
            </Text>
          </View>
          <View style={styles.progressTrack}>
            <View style={[styles.progressFill, { width: `${Math.min(100, hydration.percentage)}%` }]} />
          </View>
        </View>
      ) : null}
      {meals ? (
        <View style={styles.statTop}>
          <View style={styles.statLabelRow}>
            <Ionicons name="restaurant" size={16} color="#E0A458" />
            <Text style={styles.statLabel}>Meals</Text>
          </View>
          <Text style={styles.statValue}>{meals.completed_count} / 4 logged</Text>
        </View>
      ) : null}
      {medications ? (
        <View style={{ marginTop: spacing.sm }}>
          <View style={styles.statLabelRow}>
            <Ionicons name="medkit" size={16} color="#A07BD0" />
            <Text style={styles.statLabel}>Medications ({medications.count})</Text>
          </View>
          {medications.items.length ? (
            medications.items.map((m, i) => (
              <View key={i} style={styles.medRow}>
                <Text style={styles.medName}>
                  {m.name}
                  {m.dosage ? ` · ${m.dosage}` : ""}
                </Text>
                <View style={styles.takenChip}>
                  <Ionicons name="checkmark-circle" size={13} color={colors.status.success} />
                  <Text style={styles.takenText}>{formatTime(m.time) ? `Taken ${formatTime(m.time)}` : "Taken"}</Text>
                </View>
              </View>
            ))
          ) : (
            <Text style={styles.medEmpty}>None logged today</Text>
          )}
        </View>
      ) : null}
    </Card>
  );
}

export function TimelineSection({
  timeline,
  filteredTimeline,
  range,
  setRange,
}: {
  timeline: TimelineItem[] | null | undefined;
  filteredTimeline: TimelineItem[];
  range: RangeKey;
  setRange: (r: RangeKey) => void;
}) {
  if (!timeline) return null;
  return (
    <Card style={styles.card} testID="pv-timeline">
      <Text style={styles.sectionLabel}>Shared health timeline</Text>
      <View style={styles.segment}>
        {RANGES.map((r) => (
          <TouchableOpacity
            key={r.key}
            testID={`pv-range-${r.key}`}
            style={[styles.segBtn, range === r.key && styles.segBtnActive]}
            onPress={() => setRange(r.key)}
          >
            <Text style={[styles.segText, range === r.key && styles.segTextActive]}>{r.label}</Text>
          </TouchableOpacity>
        ))}
      </View>
      {filteredTimeline.length ? (
        filteredTimeline.map((ev) => (
          <View key={ev.id} style={styles.tlRow} testID={`pv-tl-${ev.id}`}>
            <View style={[styles.tlIcon, { backgroundColor: (TIMELINE_COLOR[ev.event_type] || colors.brand.primary) + "22" }]}>
              <Ionicons
                name={(TIMELINE_ICON[ev.event_type] || "ellipse") as any}
                size={15}
                color={TIMELINE_COLOR[ev.event_type] || colors.brand.primary}
              />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.tlSummary}>{ev.summary}</Text>
              <Text style={styles.tlDate}>
                {formatTime(ev.timestamp) ? `${formatTime(ev.timestamp)} · ` : ""}
                {formatNice(ev.date)}
              </Text>
            </View>
          </View>
        ))
      ) : (
        <Text style={styles.empty}>No shared activity in this period.</Text>
      )}
    </Card>
  );
}

export function IntimacySection({ intimacy }: { intimacy: ViewData["intimacy"] }) {
  if (!intimacy) return null;
  return (
    <Card style={styles.card} testID="pv-intimacy">
      <View style={styles.statTop}>
        <View style={styles.statLabelRow}>
          <Ionicons name="heart" size={16} color="#E8736F" />
          <Text style={styles.statLabel}>Intimacy</Text>
        </View>
        <Text style={styles.statValue}>
          {intimacy.count} {intimacy.count === 1 ? "entry" : "entries"}
        </Text>
      </View>
      {intimacy.last_date ? <Text style={styles.medEmpty}>Last: {formatNice(intimacy.last_date)}</Text> : null}
    </Card>
  );
}

export function RemindersSection({
  reminders,
  onToggle,
}: {
  reminders: PartnerReminderPrefs;
  onToggle: (key: keyof PartnerReminderPrefs) => void;
}) {
  return (
    <Card style={styles.card} testID="pv-reminders">
      <Text style={styles.sectionLabel}>Shared reminders</Text>
      <Text style={styles.helpText}>Opt in to gentle reminders on your device. You choose each one.</Text>
      {REMINDER_META.map((r) => (
        <View key={r.key} style={styles.reminderRow}>
          <View style={styles.reminderIcon}>
            <Ionicons name={r.icon as any} size={16} color={colors.brand.primary} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.reminderLabel}>{r.label}</Text>
            <Text style={styles.reminderSub}>{r.sub}</Text>
          </View>
          <Switch
            testID={`pv-reminder-${r.key}`}
            value={reminders[r.key]}
            onValueChange={() => onToggle(r.key)}
            trackColor={{ true: colors.brand.primary, false: colors.bg.tertiary }}
            thumbColor="#fff"
          />
        </View>
      ))}
      {Platform.OS === "web" ? (
        <Text style={styles.reminderNote}>Reminders are delivered on the installed mobile app.</Text>
      ) : null}
    </Card>
  );
}

export function PermissionsSection({ flags }: { flags?: Record<string, boolean> }) {
  if (!flags) return null;
  return (
    <Card style={styles.card} testID="pv-permissions">
      <Text style={styles.sectionLabel}>What you can see</Text>
      {PERMISSION_META.map((perm) => {
        const on = !!flags[perm.key];
        return (
          <View key={perm.key} style={styles.permRow} testID={`pv-perm-${perm.key}`}>
            <Ionicons
              name={on ? "checkmark-circle" : "close-circle"}
              size={18}
              color={on ? colors.status.success : colors.text.tertiary}
            />
            <Text style={[styles.permLabel, !on && { color: colors.text.tertiary }]}>{perm.label}</Text>
          </View>
        );
      })}
    </Card>
  );
}

export function LogsSection({ logs }: { logs: ViewData["logs"] }) {
  if (!logs.length) return null;
  return (
    <View>
      <Text style={styles.sectionLabel}>Shared entries</Text>
      {logs.slice(0, 30).map((l) => (
        <Card key={l.date} style={{ marginTop: spacing.sm }} testID={`pv-log-${l.date}`}>
          <Text style={styles.logDate}>{formatLong(l.date)}</Text>
          {l.moods?.length ? <Text style={styles.logText}>Moods: {l.moods.join(", ")}</Text> : null}
          {l.symptoms?.length ? (
            <Text style={styles.logText}>
              Symptoms: {l.symptoms.map((s) => `${s.name} (${s.severity})`).join(", ")}
            </Text>
          ) : null}
          {l.note ? <Text style={styles.logText}>Note: {l.note}</Text> : null}
        </Card>
      ))}
    </View>
  );
}
