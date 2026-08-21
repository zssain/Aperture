import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "../../lib/cn";

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** Only interactive cards get a hover lift — static surfaces must not look
   * clickable. */
  interactive?: boolean;
  children: ReactNode;
}

/** A bordered surface panel. Separation is by 1px border, not shadow. */
export function Card({ interactive = false, className, children, ...props }: CardProps) {
  return (
    <div
      className={cn(
        "rounded border border-border bg-surface",
        interactive &&
          "cursor-pointer transition-colors duration-fast hover:border-border-strong hover:bg-surface-subtle",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export interface SectionHeaderProps {
  eyebrow?: string;
  title: ReactNode;
  description?: ReactNode;
  /** Right-aligned actions or hints. */
  actions?: ReactNode;
  className?: string;
}

/** A header for a section within a page or card. */
export function SectionHeader({
  eyebrow,
  title,
  description,
  actions,
  className,
}: SectionHeaderProps) {
  return (
    <div className={cn("flex items-start justify-between gap-4", className)}>
      <div className="min-w-0 space-y-0.5">
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h2 className="flex items-center gap-2 text-heading font-semibold text-ink">
          {title}
        </h2>
        {description ? <p className="text-sm text-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export interface DetailRowProps {
  label: ReactNode;
  children: ReactNode;
  className?: string;
}

/** A labelled fact: label on the left, value on the right. */
export function DetailRow({ label, children, className }: DetailRowProps) {
  return (
    <div
      className={cn(
        "flex items-baseline justify-between gap-4 py-1.5 text-sm",
        className,
      )}
    >
      <dt className="text-muted">{label}</dt>
      <dd className="text-right font-medium text-ink">{children}</dd>
    </div>
  );
}
