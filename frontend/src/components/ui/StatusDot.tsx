import { cn } from "../../lib/cn";
import { dotColor, type Tone } from "./tones";

export interface StatusDotProps {
  tone: Tone;
  /** Required: a coloured dot must never convey meaning by colour alone. */
  label: string;
  className?: string;
}

export function StatusDot({ tone, label, className }: StatusDotProps) {
  return (
    <span className={cn("inline-flex items-center gap-2 text-sm text-ink", className)}>
      <span
        aria-hidden="true"
        className={cn("inline-block h-2 w-2 rounded-pill", dotColor[tone])}
      />
      <span>{label}</span>
    </span>
  );
}
