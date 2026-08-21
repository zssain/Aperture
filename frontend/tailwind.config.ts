import type { Config } from "tailwindcss";

/**
 * Locked design tokens. Arbitrary Tailwind values are forbidden — every screen must
 * compose from these. `fontSize`, `fontWeight`, `borderRadius` and `boxShadow` are
 * REPLACED (not extended) so only the sanctioned scale exists.
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    // Type scale: 30 / 24 / 18 / 15 / 13 / 12 only.
    fontSize: {
      display: ["30px", { lineHeight: "36px" }],
      title: ["24px", { lineHeight: "32px" }],
      heading: ["18px", { lineHeight: "26px" }],
      body: ["15px", { lineHeight: "22px" }],
      sm: ["13px", { lineHeight: "18px" }],
      xs: ["12px", { lineHeight: "16px" }],
    },
    // Weights 400 / 500 / 600 only.
    fontWeight: {
      normal: "400",
      medium: "500",
      semibold: "600",
    },
    // 4px radius everywhere; 999px for pills only.
    borderRadius: {
      none: "0px",
      DEFAULT: "4px",
      pill: "9999px",
    },
    // Exactly two shadows; everything else separates with 1px borders.
    boxShadow: {
      none: "none",
      drawer: "0 8px 24px rgba(15,23,42,.12)",
      modal: "0 16px 48px rgba(15,23,42,.18)",
    },
    extend: {
      screens: { "case-wide": "1440px" },
      colors: {
        surface: "#FFFFFF",
        sunken: "#F8FAFC",
        border: "#E2E8F0",
        "border-strong": "#CBD5E1",
        ink: "#0F172A",
        muted: "#64748B",
        accent: "#1E4B8F",
        positive: "#0F7B4F",
        caution: "#B45309",
        negative: "#B42318",
        // Neutral is the treatment for uncalibrated / unavailable / not-measured.
        neutral: "#475569",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
      },
      // Default border/divide colour = token border (so bare `border` uses it).
      borderColor: { DEFAULT: "#E2E8F0" },
      divideColor: { DEFAULT: "#E2E8F0" },
      ringColor: { DEFAULT: "#1E4B8F" },
      height: { row: "44px" },
      minHeight: { row: "44px" },
      maxWidth: { content: "1600px", form: "360px" },
      width: { drawer: "480px" },
      minWidth: { menu: "192px" },
    },
  },
  plugins: [],
} satisfies Config;
