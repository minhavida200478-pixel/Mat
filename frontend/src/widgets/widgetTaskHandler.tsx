/**
 * Widget Task Handler — runs headless on Android.
 * Renders widgets from the local cache and handles background click actions
 * (quick-log water/meal/period) by POSTing to the backend, then re-renders.
 */
import React from "react";
import type { WidgetTaskHandlerProps } from "react-native-android-widget";

import { HealthSummaryWidget } from "./HealthSummaryWidget";
import { QuickLogWidget } from "./QuickLogWidget";
import { NextPeriodWidget } from "./NextPeriodWidget";
import {
  readWidgetData,
  refreshWidgets,
  fetchAndCacheWidgetData,
  logWaterFromWidget,
  logMealFromWidget,
  logPeriodFromWidget,
  type WidgetData,
} from "./widgetData";

const nameToWidget = {
  HealthSummary: HealthSummaryWidget,
  QuickLog: QuickLogWidget,
  NextPeriod: NextPeriodWidget,
};

async function renderCurrent(props: WidgetTaskHandlerProps, data: WidgetData) {
  const widgetName = props.widgetInfo.widgetName as keyof typeof nameToWidget;
  const Widget = nameToWidget[widgetName];
  if (!Widget) return;
  props.renderWidget(<Widget {...data} />);
}

export async function widgetTaskHandler(props: WidgetTaskHandlerProps) {
  switch (props.widgetAction) {
    case "WIDGET_ADDED":
    case "WIDGET_UPDATE":
    case "WIDGET_RESIZED": {
      const data = await readWidgetData();
      await renderCurrent(props, data);
      break;
    }

    case "WIDGET_CLICK": {
      const action = props.clickAction;

      if (action === "LOG_WATER") {
        const amount = Number(props.clickActionData?.amount) || 250;
        await logWaterFromWidget(amount);
      } else if (action === "LOG_MEAL") {
        await logMealFromWidget();
      } else if (action === "LOG_PERIOD") {
        await logPeriodFromWidget();
      } else {
        // OPEN_APP / OPEN_URI are handled natively by the library.
        break;
      }

      // Pull authoritative numbers (streak, goal-met, etc.) after the action.
      // If the network call fails, fall back to the optimistic local cache.
      const synced = await fetchAndCacheWidgetData();
      if (!synced) await refreshWidgets();
      break;
    }

    case "WIDGET_DELETED":
    default:
      break;
  }
}
