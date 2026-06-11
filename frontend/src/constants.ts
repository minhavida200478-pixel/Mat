// Default tracking reference data
export const SYMPTOMS = [
  { name: "Cramps", icon: "flash-outline" },
  { name: "Headache", icon: "fitness-outline" },
  { name: "Acne", icon: "ellipse-outline" },
  { name: "Fatigue", icon: "battery-dead-outline" },
  { name: "Bloating", icon: "balloon-outline" },
  { name: "Nausea", icon: "sad-outline" },
  { name: "Back pain", icon: "body-outline" },
  { name: "Breast tenderness", icon: "heart-half-outline" },
];

export const MOODS = [
  { name: "Happy", icon: "happy-outline" },
  { name: "Calm", icon: "leaf-outline" },
  { name: "Irritated", icon: "thunderstorm-outline" },
  { name: "Emotional", icon: "water-outline" },
  { name: "Anxious", icon: "alert-circle-outline" },
  { name: "Energetic", icon: "sunny-outline" },
  { name: "Tired", icon: "moon-outline" },
];

export const SEVERITIES = ["mild", "moderate", "severe"] as const;
export type Severity = (typeof SEVERITIES)[number];

export const PREDICTION_DISCLAIMER =
  "Predictions are statistical estimates, not medical certainty.";
