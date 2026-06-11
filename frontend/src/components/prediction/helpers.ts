// Shared formatting + color helpers for the prediction panel sub-components.
import { colors } from "@/src/theme";

export const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return "—";
  return `${MONTHS[m - 1]} ${d}`;
}

export function confidenceColor(c: number): string {
  if (c >= 70) return colors.status.success;
  if (c >= 45) return "#C98A1E"; // amber
  return colors.status.error;
}

export function reliabilityColor(classification: string): string {
  switch (classification) {
    case "Excellent":
    case "High":
      return colors.status.success;
    case "Moderate":
      return colors.brand.primary;
    case "Low":
      return "#C98A1E"; // amber
    default:
      return colors.status.error; // Very Low
  }
}

export function daysBetween(a: string, b: string): number {
  const da = new Date(a + "T00:00:00").getTime();
  const db = new Date(b + "T00:00:00").getTime();
  return Math.round((db - da) / 86400000);
}
