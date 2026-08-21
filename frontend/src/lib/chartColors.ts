/**
 * Colours for Recharts, which needs concrete colour strings rather than Tailwind
 * classes. These MIRROR the sanctioned palette in tailwind.config.ts — keep them in
 * sync with the token hexes; do not introduce new chart-only colours.
 */
export const chartColors = {
  inflow: "#0F7B4F", // colors.positive
  outflow: "#B42318", // colors.negative
  grid: "#E2E8F0", // colors.border
  axis: "#64748B", // colors.muted
} as const;
