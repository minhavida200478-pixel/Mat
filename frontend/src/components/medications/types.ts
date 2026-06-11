// Shared medication types, constants and formatters used by the Medications
// screen and the extracted ScheduleForm component.
import { colors } from "@/src/theme";

export const ACCENT = "#9B59B6";

export type ScheduleType = "daily" | "interval" | "cycle_based";

export type Schedule = {
  id: string;
  name: string;
  dosage?: string | null;
  category: string;
  schedule_type: ScheduleType;
  times: string[];
  interval_hours?: number | null;
  interval_start?: string | null;
  cycle_days: number[];
  enabled: boolean;
};

export type Dose = {
  schedule_id: string;
  name: string;
  dosage?: string | null;
  category: string;
  time: string;
  taken: boolean;
};

export type TodayData = {
  date: string;
  doses: Dose[];
  total: number;
  taken: number;
  pending: number;
};

export type Adherence = {
  has_data: boolean;
  overall_percentage: number | null;
  expected_total: number;
  taken_total: number;
  streak_days: number;
  active_medications: number;
  medications: {
    schedule_id: string;
    name: string;
    dosage?: string | null;
    category: string;
    expected: number;
    taken: number;
    percentage: number | null;
  }[];
  recent: { date: string; expected: number; taken: number; percentage: number | null }[];
};

export const CATEGORIES = [
  { key: "painkiller", label: "Pain Relief", icon: "bandage-outline" },
  { key: "vitamin", label: "Vitamin", icon: "sunny-outline" },
  { key: "birth_control", label: "Birth Control", icon: "shield-outline" },
  { key: "hormone", label: "Hormone", icon: "fitness-outline" },
  { key: "supplement", label: "Supplement", icon: "leaf-outline" },
  { key: "other", label: "Other", icon: "medical-outline" },
];

export const COMMON_TIMES = [
  "06:00", "08:00", "09:00", "12:00", "14:00", "18:00", "20:00", "21:00", "22:00",
];
export const INTERVAL_OPTIONS = [4, 6, 8, 12];

export const fmtTime = (t: string) => {
  const [h, m] = t.split(":").map((x) => parseInt(x, 10));
  const ampm = h >= 12 ? "PM" : "AM";
  const hour12 = h % 12 === 0 ? 12 : h % 12;
  return `${hour12}:${String(m).padStart(2, "0")} ${ampm}`;
};

export const catIcon = (cat: string) =>
  CATEGORIES.find((c) => c.key === cat)?.icon ?? "medical-outline";

export const adherenceColor = (pct: number | null) => {
  if (pct === null) return colors.text.tertiary;
  if (pct >= 80) return colors.status.success;
  if (pct >= 50) return "#E0A100";
  return colors.status.periodActive;
};

export function scheduleSummary(s: Schedule): string {
  if (s.schedule_type === "interval" && s.interval_hours) {
    return `Every ${s.interval_hours}h · ${s.times.length}x/day`;
  }
  if (s.schedule_type === "cycle_based") {
    return `Cycle days ${s.cycle_days.join(", ")}`;
  }
  return s.times.length === 1 ? "Once daily" : `${s.times.length}x daily`;
}
