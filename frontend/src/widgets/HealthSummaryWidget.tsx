/**
 * Android Home Screen Widget — Health Summary
 * Today's health stats at a glance (cycle day, phase, hydration, meals, meds).
 * Data is supplied from the local widget cache (see widgetData.ts).
 */
import React from "react";
import { FlexWidget, TextWidget } from "react-native-android-widget";

import { W } from "./widgetTheme";
import type { WidgetData } from "./widgetData";

export function HealthSummaryWidget(props: Partial<WidgetData>) {
  const {
    hasData = false,
    hydration = 0,
    hydrationGoal = 2000,
    hydrationGoalMet = false,
    mealsLogged = 0,
    medicationsTaken = 0,
    cycleDay = 0,
    phase = "Get started",
    streakDays = 0,
  } = props;

  const hydrationPercent =
    hydrationGoal > 0 ? Math.min(100, Math.round((hydration / hydrationGoal) * 100)) : 0;

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
      {/* Header */}
      <FlexWidget
        style={{
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <TextWidget
          text="Cycle Health"
          style={{ fontSize: 14, fontWeight: "600", color: W.accent }}
        />
        <FlexWidget
          style={{
            backgroundColor: W.card,
            borderRadius: 12,
            paddingHorizontal: 10,
            paddingVertical: 4,
          }}
        >
          <TextWidget
            text={hasData && cycleDay > 0 ? `Day ${cycleDay}` : "No data"}
            style={{ fontSize: 12, fontWeight: "600", color: W.accent }}
          />
        </FlexWidget>
      </FlexWidget>

      {/* Phase + engagement streak */}
      <FlexWidget
        style={{
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "space-between",
          marginTop: 4,
        }}
      >
        <TextWidget
          text={phase}
          style={{ fontSize: 18, fontWeight: "700", color: W.text }}
        />
        {streakDays > 0 ? (
          <FlexWidget
            style={{
              backgroundColor: W.meal,
              borderRadius: 10,
              paddingHorizontal: 8,
              paddingVertical: 3,
            }}
          >
            <TextWidget
              text={`${streakDays}-day streak`}
              style={{ fontSize: 11, fontWeight: "700", color: W.bg }}
            />
          </FlexWidget>
        ) : null}
      </FlexWidget>

      {/* Stats Row */}
      <FlexWidget
        style={{
          flexDirection: "row",
          justifyContent: "space-between",
          marginTop: 12,
        }}
      >
        {/* Hydration */}
        <FlexWidget
          style={{
            flex: 1,
            backgroundColor: W.card,
            borderRadius: 12,
            padding: 10,
            marginRight: 6,
            alignItems: "center",
          }}
        >
          <TextWidget text="Water" style={{ fontSize: 10, color: W.textDim }} />
          <TextWidget
            text={`${hydrationPercent}%`}
            style={{
              fontSize: 17,
              fontWeight: "700",
              color: hydrationGoalMet ? W.success : W.water,
              marginTop: 2,
            }}
          />
          <TextWidget
            text={hydrationGoalMet ? "Goal met" : `${hydration}ml`}
            style={{
              fontSize: 9,
              color: hydrationGoalMet ? W.success : W.textDim,
              marginTop: 1,
            }}
          />
        </FlexWidget>

        {/* Meals */}
        <FlexWidget
          style={{
            flex: 1,
            backgroundColor: W.card,
            borderRadius: 12,
            padding: 10,
            marginHorizontal: 3,
            alignItems: "center",
          }}
        >
          <TextWidget text="Meals" style={{ fontSize: 10, color: W.textDim }} />
          <TextWidget
            text={`${mealsLogged}/4`}
            style={{ fontSize: 17, fontWeight: "700", color: W.meal, marginTop: 2 }}
          />
          <TextWidget text="logged" style={{ fontSize: 9, color: W.textDim, marginTop: 1 }} />
        </FlexWidget>

        {/* Medications */}
        <FlexWidget
          style={{
            flex: 1,
            backgroundColor: W.card,
            borderRadius: 12,
            padding: 10,
            marginLeft: 6,
            alignItems: "center",
          }}
        >
          <TextWidget text="Meds" style={{ fontSize: 10, color: W.textDim }} />
          <TextWidget
            text={`${medicationsTaken}`}
            style={{ fontSize: 17, fontWeight: "700", color: W.med, marginTop: 2 }}
          />
          <TextWidget text="taken" style={{ fontSize: 9, color: W.textDim, marginTop: 1 }} />
        </FlexWidget>
      </FlexWidget>
    </FlexWidget>
  );
}
