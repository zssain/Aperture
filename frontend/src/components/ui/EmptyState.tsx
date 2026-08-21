import type { ReactNode } from "react";

import { cn } from "../../lib/cn";

export interface EmptyStateProps {
  /** What is missing. */
  title: string;
  /** Why it is missing. */
  description: string;
  /** Exactly one action. */
  action?: ReactNode;
  className?: string;
}

/** Three lines and at most one action. No illustration. */
export function EmptyState({ title, description, action, className }: EmptyStateProps) {
  return (
    <div
      role="status"
      className={cn(
        "flex flex-col items-start gap-3 rounded border border-dashed border-border-strong bg-surface p-6",
        className,
      )}
    >
      <div className="space-y-1">
        <p className="text-heading font-semibold text-ink">{title}</p>
        <p className="text-sm text-muted">{description}</p>
      </div>
      {action}
    </div>
  );
}
