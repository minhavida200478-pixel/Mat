/**
 * Android Home Screen Widget — Next Period countdown
 * Compact widget showing days until the next predicted period + the date & phase.
 */
import React from "react";
import { FlexWidget, TextWidget } from "react-native-android-widget";

import { W } from "./widgetTheme";
import type { WidgetData } from "./widgetData";

function formatNice(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function countdownLabel(days: number | null): { big: string; small: string } {
  if (days === null) return { big: "—", small: "No prediction yet" };
  if (days > 1) return { big: `${days}`, small: "days until period" };
  if (days === 1) return { big: "1", small: "day until period" };
  if (days === 0) return { big: "Today", small: "Period expected" };
  return { big: `${Math.abs(days)}`, small: "days late" };
}

export function NextPeriodWidget(props: Partial<WidgetData>) {
  const { hasData = false, daysUntilNextPeriod = null, nextPeriodDate = null, phase = "" } = props;

  const isLate = daysUntilNextPeriod !== null && daysUntilNextPeriod < 0;
  const accent = isLate ? W.period : W.accent;
  const { big, small } = countdownLabel(hasData ? daysUntilNextPeriod : null);

  return (
    <FlexWidget
      style={{
        height: "match_parent",
        width: "match_parent",
        backgroundColor: W.bg,
        borderRadius: 24,
        padding: 16,
        flexDirection: "column",
        justifyContent: "space-between",
      }}
      clickAction="OPEN_APP"
    >
      <FlexWidget
        style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}
      >
        <TextWidget
          text="Next Period"
          style={{ fontSize: 13, fontWeight: "600", color: W.period }}
        />
        <TextWidget
          text={hasData ? formatNice(nextPeriodDate) : "Set up"}
          style={{ fontSize: 12, fontWeight: "600", color: W.textDim }}
        />
      </FlexWidget>

      {hasData ? (
        <FlexWidget style={{ flexDirection: "row", alignItems: "flex-end", marginTop: 4 }}>
          <TextWidget
            text={big}
            style={{ fontSize: 40, fontWeight: "700", color: accent }}
          />
          <TextWidget
            text={small}
            style={{ fontSize: 12, color: W.textDim, marginLeft: 8, marginBottom: 8 }}
          />
        </FlexWidget>
      ) : (
        <TextWidget
          text="Log your first period to see predictions"
          style={{ fontSize: 14, color: W.text, marginTop: 6 }}
        />
      )}

      <FlexWidget
        style={{
          backgroundColor: W.card,
          borderRadius: 12,
          paddingHorizontal: 10,
          paddingVertical: 6,
          alignItems: "center",
        }}
      >
        <TextWidget
          text={phase || "Tap to open"}
          style={{ fontSize: 12, fontWeight: "600", color: W.accent }}
        />
      </FlexWidget>
    </FlexWidget>
  );
}
