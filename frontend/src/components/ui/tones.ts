import type { IconName } from "./Icon";

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

/** Tinted label treatment (Badge / Chip): a subtle fill with a strong foreground,
 * no hard outline. Reads calmer and denser than the old bordered style. */
export const badgeTone: Record<Tone, string> = {
  neutral: "bg-neutral-subtle text-neutral",
  positive: "bg-positive-subtle text-positive",
  caution: "bg-caution-subtle text-caution",
  negative: "bg-negative-subtle text-negative",
  accent: "bg-accent-subtle text-accent",
  muted: "bg-sunken text-muted",
};

/** Optional glyph so a pass/fail status never rides on colour alone. */
export const toneGlyph: Record<Tone, IconName> = {
  neutral: "info",
  positive: "check",
  caution: "alert",
  negative: "alert",
  accent: "info",
  muted: "info",
};
