import type { ReactNode } from "react";

import { cn } from "../../lib/cn";
import { Icon } from "./Icon";
import { badgeTone, toneGlyph, type Tone } from "./tones";

export interface ChipProps {
  tone?: Tone;
  /** When true, prefixes the tone's glyph so status never rides on colour alone. */
  glyph?: boolean;
  children: ReactNode;
  className?: string;
}

/** A compact pill-shaped tag (e.g. the UNCAL marker). */
export function Chip({ tone = "neutral", glyph = false, children, className }: ChipProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-pill px-2 py-0.5 text-xs font-medium",
        badgeTone[tone],
        className,
      )}
    >
      {glyph ? <Icon name={toneGlyph[tone]} size={13} /> : null}
      {children}
    </span>
  );
}
