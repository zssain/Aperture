import type { ReactNode } from "react";

import { cn } from "../../lib/cn";

export interface PageHeaderProps {
  /** Small uppercase context label above the title. */
  eyebrow?: string;
  title: string;
  description?: string;
  /** Right-aligned actions (buttons). */
  actions?: ReactNode;
  /** Optional content below the divider (filters, tabs). */
  children?: ReactNode;
  className?: string;
}

/** The standard screen header: eyebrow / title / description, right-aligned
 * actions, a divider, and optional children below it. */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  children,
  className,
}: PageHeaderProps) {
  return (
    <header className={cn("mb-6", className)}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 space-y-1">
          {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
          <h1 className="text-title font-semibold text-ink">{title}</h1>
          {description ? (
            <p className="max-w-2xl text-sm text-muted">{description}</p>
          ) : null}
        </div>
        {actions ? (
          <div className="flex shrink-0 items-center gap-2">{actions}</div>
        ) : null}
      </div>
      <div className="mt-4 border-b border-border" />
      {children ? <div className="mt-4">{children}</div> : null}
    </header>
  );
}
