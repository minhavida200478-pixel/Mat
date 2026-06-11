import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useMemo, useState } from "react";
import {
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { api } from "@/src/api/client";
import { DayEvents } from "@/src/components/calendar/DayEvents";
import { HealthEvent } from "@/src/components/calendar/eventUtils";
import { Card } from "@/src/components/ui";
import { colors, radius, spacing, type } from "@/src/theme";
import { phaseForDate, Prediction, todayISO } from "@/src/utils/cycle";

const WEEKDAYS = ["S", "M", "T", "W", "T", "F", "S"];
const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

export default function Calendar() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const now = new Date();
  const [month, setMonth] = useState(now.getMonth());
  const [year, setYear] = useState(now.getFullYear());
  const [prediction, setPrediction] = useState<Prediction | undefined>();
  const [events, setEvents] = useState<HealthEvent[]>([]);
  const [selected, setSelected] = useState<string>(todayISO());

  const load = useCallback(async () => {
    const mm = String(month + 1).padStart(2, "0");
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const startDate = `${year}-${mm}-01`;
    const endDate = `${year}-${mm}-${String(daysInMonth).padStart(2, "0")}`;
    try {
      const [dash, evList] = await Promise.all([
        api.get("/dashboard"),
        api.get<HealthEvent[]>(
          `/health-events?start_date=${startDate}&end_date=${endDate}&limit=500`,
        ),
      ]);
      setPrediction(dash.prediction);
      setEvents(evList);
    } catch {
      /* ignore */
    }
  }, [month, year]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const eventsByDate = useMemo(() => {
    const map: Record<string, HealthEvent[]> = {};
    events.forEach((e) => {
      (map[e.date] = map[e.date] || []).push(e);
    });
    return map;
  }, [events]);

  const cells = useMemo(() => {
    const first = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const arr: (string | null)[] = [];
    for (let i = 0; i < first; i++) arr.push(null);
    for (let d = 1; d <= daysInMonth; d++) {
      const iso = `${year}-${String(month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      arr.push(iso);
    }
    return arr;
  }, [month, year]);

  function changeMonth(delta: number) {
    let m = month + delta;
    let y = year;
    if (m < 0) {
      m = 11;
      y -= 1;
    } else if (m > 11) {
      m = 0;
      y += 1;
    }
    setMonth(m);
    setYear(y);
  }

  const handleDeleted = useCallback((id: string) => {
    setEvents((prev) => prev.filter((e) => e.id !== id));
  }, []);

  const selectedEvents = eventsByDate[selected] || [];

  return (
    <ScrollView
      testID="calendar-screen"
      style={styles.screen}
      contentContainerStyle={{ paddingBottom: spacing.xxl, paddingTop: insets.top + spacing.md }}
    >
      <Text style={styles.title}>Calendar</Text>

      <Card style={styles.calCard}>
        <View style={styles.monthRow}>
          <TouchableOpacity testID="cal-prev-month" onPress={() => changeMonth(-1)} style={styles.navBtn}>
            <Ionicons name="chevron-back" size={20} color={colors.text.secondary} />
          </TouchableOpacity>
          <Text style={styles.monthLabel} testID="cal-month-label">
            {MONTHS[month]} {year}
          </Text>
          <TouchableOpacity testID="cal-next-month" onPress={() => changeMonth(1)} style={styles.navBtn}>
            <Ionicons name="chevron-forward" size={20} color={colors.text.secondary} />
          </TouchableOpacity>
        </View>

        <View style={styles.weekRow}>
          {WEEKDAYS.map((w, i) => (
            <Text key={i} style={styles.weekday}>
              {w}
            </Text>
          ))}
        </View>

        <View style={styles.grid}>
          {cells.map((iso, i) => {
            if (!iso) return <View key={i} style={styles.cell} />;
            const phase = phaseForDate(iso, prediction);
            const isToday = iso === todayISO();
            const isSelected = iso === selected;
            const hasEvents = !!eventsByDate[iso]?.length;
            const dayNum = parseInt(iso.slice(-2), 10);
            let bg = "transparent";
            let textColor = colors.text.primary;
            if (phase === "period") {
              bg = colors.status.periodLight;
              textColor = colors.status.periodActive;
            } else if (phase === "fertile" || phase === "ovulation") {
              bg = colors.status.fertileLight;
              textColor = colors.status.fertile;
            }
            return (
              <TouchableOpacity
                key={i}
                testID={`calendar-day-${dayNum}`}
                style={styles.cell}
                activeOpacity={0.6}
                onPress={() => setSelected(iso)}
              >
                <View
                  style={[
                    styles.dayCircle,
                    { backgroundColor: bg },
                    isSelected && styles.daySelected,
                  ]}
                >
                  <Text
                    style={[
                      styles.dayText,
                      { color: isSelected ? "#fff" : textColor },
                      isToday && !isSelected && styles.todayText,
                    ]}
                  >
                    {dayNum}
                  </Text>
                </View>
                {hasEvents ? <View style={styles.logDot} /> : <View style={styles.logDotEmpty} />}
              </TouchableOpacity>
            );
          })}
        </View>
      </Card>

      <View style={styles.legendRow}>
        <Legend color={colors.status.periodActive} label="Period" />
        <Legend color={colors.status.fertile} label="Fertile" />
        <Legend color={colors.brand.primary} label="Logged" />
      </View>

      <Card style={{ marginHorizontal: spacing.screen, marginTop: spacing.md }} testID="calendar-day-detail">
        <View style={styles.detailHeader}>
          <Text style={styles.detailDate}>
            {new Date(selected + "T00:00:00").toLocaleDateString(undefined, {
              weekday: "long",
              month: "long",
              day: "numeric",
            })}
          </Text>
          <TouchableOpacity
            testID="calendar-edit-day"
            onPress={() => router.push(`/log?date=${selected}`)}
            style={styles.editBtn}
          >
            <Ionicons name="create-outline" size={16} color={colors.brand.primary} />
            <Text style={styles.editText}>Log</Text>
          </TouchableOpacity>
        </View>

        <DayEvents events={selectedEvents} onDeleted={handleDeleted} />
      </Card>
    </ScrollView>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <View style={styles.legendItem}>
      <View style={[styles.legendDot, { backgroundColor: color }]} />
      <Text style={styles.legendLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg.primary },
  title: { ...type.h1, color: colors.text.primary, paddingHorizontal: spacing.screen, marginBottom: spacing.md },
  calCard: { marginHorizontal: spacing.screen, padding: spacing.md },
  monthRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  navBtn: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.bg.secondary, alignItems: "center", justifyContent: "center" },
  monthLabel: { ...type.h3, color: colors.text.primary },
  weekRow: { flexDirection: "row", marginBottom: spacing.sm },
  weekday: { flex: 1, textAlign: "center", ...type.caption, color: colors.text.tertiary },
  grid: { flexDirection: "row", flexWrap: "wrap" },
  cell: { width: `${100 / 7}%`, aspectRatio: 1, alignItems: "center", justifyContent: "center" },
  dayCircle: { width: 38, height: 38, borderRadius: 19, alignItems: "center", justifyContent: "center" },
  daySelected: { backgroundColor: colors.brand.primary },
  dayText: { fontSize: 15, fontWeight: "500" },
  todayText: { fontWeight: "800", textDecorationLine: "underline" },
  logDot: { width: 5, height: 5, borderRadius: 3, backgroundColor: colors.brand.primary, marginTop: 3 },
  logDotEmpty: { width: 5, height: 5, marginTop: 3 },
  legendRow: { flexDirection: "row", justifyContent: "center", gap: spacing.lg, marginTop: spacing.md },
  legendItem: { flexDirection: "row", alignItems: "center" },
  legendDot: { width: 10, height: 10, borderRadius: 5, marginRight: 6 },
  legendLabel: { ...type.bodySm, color: colors.text.secondary },
  detailHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  detailDate: { ...type.h3, color: colors.text.primary, flex: 1 },
  editBtn: { flexDirection: "row", alignItems: "center", backgroundColor: colors.brand.primaryLight, paddingHorizontal: 12, paddingVertical: 6, borderRadius: radius.pill },
  editText: { color: colors.brand.primary, fontWeight: "600", marginLeft: 4, fontSize: 13 },
});
