import type { Config } from "tailwindcss";

/**
 * Locked design tokens. Arbitrary Tailwind values are forbidden — every screen must
 * compose from these. `fontSize`, `fontWeight`, `borderRadius` and `boxShadow` are
 * REPLACED (not extended) so only the sanctioned scale exists.
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    // Type scale: 30 / 24 / 18 / 15 / 13 / 12 / 11 (eyebrow) only.
    fontSize: {
      display: ["30px", { lineHeight: "36px" }],
      title: ["24px", { lineHeight: "32px" }],
      heading: ["18px", { lineHeight: "26px" }],
      body: ["15px", { lineHeight: "22px" }],
      sm: ["13px", { lineHeight: "18px" }],
      xs: ["12px", { lineHeight: "16px" }],
      // Small uppercase section labels (eyebrows) and table column heads.
      eyebrow: ["11px", { lineHeight: "16px", letterSpacing: "0.06em" }],
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
        // A faint raised surface for zebra rows and inset panels.
        "surface-subtle": "#FBFCFE",
        sunken: "#F8FAFC",
        subtle: "#94A3B8",
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
        // Subtle semantic fills — badges/tiles tint rather than outline. Derived
        // from the foreground hues above at ~10% toward white.
        "positive-subtle": "#E6F4EE",
        "caution-subtle": "#FBF0E1",
        "negative-subtle": "#FBEAE8",
        "accent-subtle": "#E8EEF7",
        "neutral-subtle": "#EEF1F5",
        // Navigation surfaces, derived from the brand navy #0F1D2E.
        nav: "#0F1D2E",
        "nav-raised": "#1A2C40",
        "nav-border": "#243449",
        "nav-fg": "#F1F5F9",
        "nav-muted": "#93A3B8",
        // Brand teal — used for the active-nav rail and the light wordmark.
        brand: "#109E77",
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
      maxWidth: {
        content: "1600px",
        form: "360px",
        // Keep an overlay inside the viewport with a comfortable gutter.
        "screen-safe": "calc(100vw - 2rem)",
      },
      maxHeight: {
        // Modal body: full height minus a top/bottom gutter.
        overlay: "calc(100vh - 4rem)",
      },
      width: {
        drawer: "480px",
        "modal-sm": "384px",
        "modal-lg": "640px",
      },
      minWidth: { menu: "192px" },
      // Sidebar width lives on the SPACING scale so both `w-sidebar` and
      // `pl-sidebar` compose from one token.
      spacing: { sidebar: "248px" },
      transitionDuration: {
        // ~120ms hover/focus/press · ~180ms menus/tabs/tooltips · ~240ms overlays.
        fast: "120ms",
        menu: "180ms",
        overlay: "240ms",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "modal-in": {
          from: { opacity: "0", transform: "translate(-50%, -50%) scale(0.98)" },
          to: { opacity: "1", transform: "translate(-50%, -50%) scale(1)" },
        },
        "drawer-in": {
          from: { transform: "translateX(-100%)" },
          to: { transform: "translateX(0)" },
        },
        "sheet-in": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-in": "fade-in 180ms ease-out",
        "modal-in": "modal-in 240ms cubic-bezier(0.16, 1, 0.3, 1)",
        "drawer-in": "drawer-in 240ms cubic-bezier(0.16, 1, 0.3, 1)",
        "sheet-in": "sheet-in 180ms ease-out",
      },
    },
  },
  plugins: [],
} satisfies Config;
