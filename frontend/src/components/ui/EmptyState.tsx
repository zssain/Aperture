import type { ReactNode } from "react";

import { cn } from "../../lib/cn";
import { Icon, type IconName } from "./Icon";

export interface EmptyStateProps {
  /** What is missing. */
  title: string;
  /** Why it is missing. */
  description: string;
  /** A single restrained glyph. No illustration. */
  icon?: IconName;
  /** Exactly one action. */
  action?: ReactNode;
  className?: string;
}

/** A single glyph, three lines and at most one action. No illustration. */
export function EmptyState({
  title,
  description,
  icon = "info",
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      role="status"
      className={cn(
        "flex flex-col items-start gap-3 rounded border border-dashed border-border-strong bg-surface p-6",
        className,
      )}
    >
      <span className="flex h-9 w-9 items-center justify-center rounded-pill bg-sunken text-muted">
        <Icon name={icon} size={18} />
      </span>
      <div className="space-y-1">
        <p className="text-heading font-semibold text-ink">{title}</p>
        <p className="text-sm text-muted">{description}</p>
      </div>
      {action}
    </div>
  );
}
