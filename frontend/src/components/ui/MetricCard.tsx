import type { ReactNode } from "react";

import { cn } from "../../lib/cn";
import type { Tone } from "./tones";

/** Left-rail colour per tone. Tone paints the rail only — never the value — so an
 * uncalibrated or independent reading is not made to look like an aggregate score. */
const RAIL: Record<Tone, string> = {
  neutral: "bg-neutral",
  positive: "bg-positive",
  caution: "bg-caution",
  negative: "bg-negative",
  accent: "bg-accent",
  muted: "bg-border-strong",
};

export interface MetricCardProps {
  label: ReactNode;
  /** The primary value. Kept in ink regardless of tone. */
  value: ReactNode;
  /** Optional supporting line below the value. */
  hint?: ReactNode;
  /** Tone colours the left rail only. */
  tone?: Tone;
  className?: string;
}

/** A compact metric tile: a tone rail, a label and a value that stays in ink. */
export function MetricCard({
  label,
  value,
  hint,
  tone = "neutral",
  className,
}: MetricCardProps) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded border border-border bg-surface p-4 pl-5",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className={cn("absolute inset-y-0 left-0 w-1", RAIL[tone])}
      />
      <div className="flex items-center gap-1.5 text-sm text-muted">{label}</div>
      <div className="mt-1 text-heading font-semibold text-ink">{value}</div>
      {hint ? <div className="mt-1 text-xs text-muted">{hint}</div> : null}
    </div>
  );
}
