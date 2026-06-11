// Design tokens — Calming Teal, medical-grade minimalism. Translated from design_guidelines.json
export const colors = {
  bg: {
    primary: "#FFFFFF",
    secondary: "#F5F7F8",
    tertiary: "#EBEFEF",
  },
  brand: {
    primary: "#2A7A78",
    primaryLight: "#DEF2F1",
    indigo: "#1F3A5F",
    indigoLight: "#E8ECF1",
  },
  text: {
    primary: "#1A2526",
    secondary: "#576A6B",
    tertiary: "#8A9F9F",
    inverse: "#FFFFFF",
  },
  status: {
    periodActive: "#D9534F",
    periodLight: "#FADBD8",
    fertile: "#5C9EAD",
    fertileLight: "#E0F0F2",
    success: "#3F8A6B",
    error: "#C64646",
  },
  ui: {
    border: "#E2E8E8",
    divider: "#F0F4F4",
    overlay: "rgba(26, 37, 38, 0.4)",
  },
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
  screen: 24,
};

export const radius = {
  sm: 8,
  md: 12,
  lg: 16,
  pill: 24,
  round: 999,
};

export const type = {
  h1: { fontSize: 32, lineHeight: 40, letterSpacing: -0.5, fontWeight: "700" as const },
  h2: { fontSize: 24, lineHeight: 32, letterSpacing: -0.3, fontWeight: "600" as const },
  h3: { fontSize: 20, lineHeight: 28, letterSpacing: -0.2, fontWeight: "600" as const },
  bodyLg: { fontSize: 18, lineHeight: 26, fontWeight: "400" as const },
  body: { fontSize: 16, lineHeight: 24, fontWeight: "400" as const },
  bodySm: { fontSize: 14, lineHeight: 20, fontWeight: "400" as const },
  caption: {
    fontSize: 12,
    lineHeight: 16,
    letterSpacing: 0.5,
    fontWeight: "500" as const,
    textTransform: "uppercase" as const,
  },
};

export const media = {
  onboardingBg:
    "https://static.prod-images.emergentagent.com/jobs/baa58e36-49a4-4e78-8a97-7b22765e67a4/images/2c4dda9da70095ebf0328c41167bd8074aa88690c7c7cd6724b59d787f0f1456.png",
  privacyShield:
    "https://static.prod-images.emergentagent.com/jobs/baa58e36-49a4-4e78-8a97-7b22765e67a4/images/655f66631e2bd86cb18d318d3ed48652272a6f86200140c294069bca8f71effe.png",
  cycleRingBg:
    "https://static.prod-images.emergentagent.com/jobs/baa58e36-49a4-4e78-8a97-7b22765e67a4/images/4ed4a59f2b747928e61c38a17f3fbd14706581433f2a1dd82e51178d5ba0e58b.png",
  journalTexture:
    "https://images.pexels.com/photos/3394939/pexels-photo-3394939.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
};
