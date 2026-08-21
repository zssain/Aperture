/** Semantic tones shared by Badge, Chip and StatusDot. Neutral = uncalibrated /
 * unavailable / not-measured. */
export type Tone =
  | "neutral"
  | "positive"
  | "caution"
  | "negative"
  | "accent"
  | "muted";

/** Background colour for a solid dot. */
export const dotColor: Record<Tone, string> = {
  neutral: "bg-neutral",
  positive: "bg-positive",
  caution: "bg-caution",
  negative: "bg-negative",
  accent: "bg-accent",
  muted: "bg-muted",
};

/** Bordered label treatment (Badge / Chip). */
export const badgeTone: Record<Tone, string> = {
  neutral: "bg-sunken text-neutral border-border-strong",
  positive: "bg-surface text-positive border-positive",
  caution: "bg-surface text-caution border-caution",
  negative: "bg-surface text-negative border-negative",
  accent: "bg-surface text-accent border-accent",
  muted: "bg-sunken text-muted border-border",
};
