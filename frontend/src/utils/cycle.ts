// Pure helpers for cycle phase + date formatting (mirrors backend logic for UI labels).
export type Prediction = {
  has_data: boolean;
  avg_cycle_length: number;
  avg_period_length: number;
  last_period_start?: string;
  cycle_day?: number;
  next_period_date?: string;
  days_until_next_period?: number;
  ovulation_date?: string;
  fertile_window_start?: string;
  fertile_window_end?: string;
  total_cycles_tracked?: number;
};

export function todayISO(): string {
  // Device-LOCAL calendar date (not UTC) so "today" matches what the user sees
  // and stays consistent with the date logs are filed under.
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate(),
  ).padStart(2, "0")}`;
}

export function formatNice(iso?: string): string {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function formatLong(iso?: string): string {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}

function within(target: string, start?: string, end?: string): boolean {
  if (!start || !end) return false;
  return target >= start && target <= end;
}

// Returns phase label for a given ISO date based on prediction.
export function phaseForDate(iso: string, p?: Prediction): "period" | "fertile" | "ovulation" | "none" {
  if (!p || !p.has_data) return "none";
  if (within(iso, p.fertile_window_start, p.fertile_window_end)) {
    if (p.ovulation_date && iso === p.ovulation_date) return "ovulation";
    return "fertile";
  }
  // approximate predicted period window: next_period_date for avg_period_length days
  if (p.next_period_date) {
    const start = p.next_period_date;
    const end = addDays(p.next_period_date, (p.avg_period_length || 5) - 1);
    if (within(iso, start, end)) return "period";
  }
  return "none";
}

export function addDays(iso: string, days: number): string {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

export function currentPhaseLabel(p?: Prediction): { phase: string; sub: string } {
  if (!p || !p.has_data) {
    return { phase: "Get started", sub: "Log your first period" };
  }
  const today = todayISO();
  const ph = phaseForDate(today, p);
  if (ph === "period") return { phase: "Menstrual", sub: "Period predicted" };
  if (ph === "ovulation") return { phase: "Ovulation", sub: "Peak fertility today" };
  if (ph === "fertile") return { phase: "Fertile window", sub: "Higher chance of conception" };
  const d = p.days_until_next_period;
  if (typeof d === "number") {
    if (d > 0) return { phase: "Follicular / Luteal", sub: `Period in ${d} days` };
    if (d === 0) return { phase: "Period due", sub: "Expected today" };
    return { phase: "Late", sub: `${Math.abs(d)} days late` };
  }
  return { phase: "Tracking", sub: "" };
}
