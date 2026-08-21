import type { ReactNode } from "react";

import { cn } from "../../lib/cn";
import { badgeTone, type Tone } from "./tones";

export interface BadgeProps {
  tone?: Tone;
  children: ReactNode;
  className?: string;
}

/** A small, square-cornered status label. */
export function Badge({ tone = "neutral", children, className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium",
        badgeTone[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
