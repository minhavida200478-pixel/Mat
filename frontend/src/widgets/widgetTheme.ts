// Shared color palette for Android home-screen widgets.
// Tuned for a dark widget surface while staying in the app's calming-teal brand family.
export const W = {
  bg: "#15302E", // deep teal surface
  card: "#1E403D", // raised card on the surface
  cardAlt: "#24524E",
  accent: "#5FBDB8", // bright teal (reads well on dark)
  accentSoft: "#2A7A78",
  text: "#FFFFFF",
  textDim: "#9DBDBA",
  period: "#E8736F",
  periodSoft: "#3A2A2C",
  water: "#5C9EAD",
  meal: "#E0A458",
  med: "#A99BE0",
  success: "#5FC79B",
} as const;

// Deep links into the app (expo-router resolves the path after the scheme).
export const DEEP_LINK = {
  home: "cyclehealth:///",
  log: "cyclehealth:///log",
  calendar: "cyclehealth:///calendar",
};
