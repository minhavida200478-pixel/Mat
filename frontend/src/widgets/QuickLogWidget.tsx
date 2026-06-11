/**
 * Android Home Screen Widget — Quick Log
 * One-tap logging actions fired directly from the home screen.
 * Water/Meal/Period buttons run as background actions (handled in widgetTaskHandler);
 * Medication opens the app since it needs detailed input.
 */
import React from "react";
import { FlexWidget, TextWidget } from "react-native-android-widget";
import type { ColorProp } from "react-native-android-widget";

import { W } from "./widgetTheme";
import type { WidgetData } from "./widgetData";

function ActionButton({
  label,
  color,
  clickAction,
  clickActionData,
  flex = 1,
  marginLeft = 0,
  marginRight = 0,
  marginTop = 0,
}: {
  label: string;
  color: ColorProp;
  clickAction: string;
  clickActionData?: Record<string, unknown>;
  flex?: number;
  marginLeft?: number;
  marginRight?: number;
  marginTop?: number;
}) {
  return (
    <FlexWidget
      style={{
        flex,
        backgroundColor: color,
        borderRadius: 12,
        height: 44,
        marginLeft,
        marginRight,
        marginTop,
        alignItems: "center",
        justifyContent: "center",
      }}
      clickAction={clickAction}
      clickActionData={clickActionData}
    >
      <TextWidget
        text={label}
        style={{ fontSize: 13, fontWeight: "600", color: W.text }}
      />
    </FlexWidget>
  );
}

export function QuickLogWidget(props: Partial<WidgetData>) {
  const { streakDays = 0, hydrationGoalMet = false } = props;
  return (
    <FlexWidget
      style={{
        height: "match_parent",
        width: "match_parent",
        backgroundColor: W.bg,
        borderRadius: 24,
        padding: 12,
        flexDirection: "column",
      }}
    >
      {/* Header: title + engagement (streak / goal-met) */}
      <FlexWidget
        style={{
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 8,
        }}
      >
        <TextWidget
          text="Quick Log"
          style={{ fontSize: 14, fontWeight: "600", color: W.accent }}
        />
        <FlexWidget style={{ flexDirection: "row", alignItems: "center" }}>
          {streakDays > 0 ? (
            <FlexWidget
              style={{
                backgroundColor: W.meal,
                borderRadius: 10,
                paddingHorizontal: 8,
                paddingVertical: 3,
                marginRight: hydrationGoalMet ? 6 : 0,
              }}
            >
              <TextWidget
                text={`${streakDays}-day streak`}
                style={{ fontSize: 11, fontWeight: "700", color: W.bg }}
              />
            </FlexWidget>
          ) : null}
          {hydrationGoalMet ? (
            <FlexWidget
              style={{
                backgroundColor: W.success,
                borderRadius: 10,
                paddingHorizontal: 8,
                paddingVertical: 3,
              }}
            >
              <TextWidget
                text="Goal met"
                style={{ fontSize: 11, fontWeight: "700", color: W.bg }}
              />
            </FlexWidget>
          ) : null}
        </FlexWidget>
      </FlexWidget>

      <FlexWidget style={{ flex: 1, flexDirection: "column", justifyContent: "space-around" }}>
        {/* Water row */}
        <FlexWidget style={{ flexDirection: "row", justifyContent: "space-between" }}>
          <ActionButton
            label="+250ml"
            color={W.water}
            clickAction="LOG_WATER"
            clickActionData={{ amount: 250 }}
            marginRight={4}
          />
          <ActionButton
            label="+500ml"
            color={W.water}
            clickAction="LOG_WATER"
            clickActionData={{ amount: 500 }}
            marginLeft={4}
          />
        </FlexWidget>

        {/* Meal & Meds row */}
        <FlexWidget style={{ flexDirection: "row", justifyContent: "space-between", marginTop: 8 }}>
          <ActionButton label="Meal" color={W.meal} clickAction="LOG_MEAL" marginRight={4} />
          <ActionButton label="Med" color={W.med} clickAction="OPEN_APP" marginLeft={4} />
        </FlexWidget>

        {/* Period button */}
        <ActionButton
          label="Log Period"
          color={W.period}
          clickAction="LOG_PERIOD"
          marginTop={8}
        />
      </FlexWidget>
    </FlexWidget>
  );
}
