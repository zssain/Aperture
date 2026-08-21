import type { ReactNode } from "react";

import { cn } from "../../lib/cn";
import { Icon } from "./Icon";
import { badgeTone, toneGlyph, type Tone } from "./tones";

export interface BadgeProps {
  tone?: Tone;
  /** When true, prefixes the tone's glyph so status never rides on colour alone. */
  glyph?: boolean;
  children: ReactNode;
  className?: string;
}

/** A small, square-cornered status label with a tinted fill. */
export function Badge({ tone = "neutral", glyph = false, children, className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium",
        badgeTone[tone],
        className,
      )}
    >
      {glyph ? <Icon name={toneGlyph[tone]} size={13} /> : null}
      {children}
    </span>
  );
}
