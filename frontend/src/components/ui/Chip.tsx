import type { ReactNode } from "react";

import { cn } from "../../lib/cn";
import { badgeTone, type Tone } from "./tones";

export interface ChipProps {
  tone?: Tone;
  children: ReactNode;
  className?: string;
}

/** A compact pill-shaped tag (e.g. the UNCAL marker). */
export function Chip({ tone = "neutral", children, className }: ChipProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-pill border px-2 py-0.5 text-xs font-medium",
        badgeTone[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
