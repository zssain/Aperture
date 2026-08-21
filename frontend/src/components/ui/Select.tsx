import type { SelectHTMLAttributes } from "react";
import { forwardRef } from "react";

import { cn } from "../../lib/cn";

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  invalid?: boolean;
}

/** Native <select> — accessible by default; no overlay library needed. */
export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { className, invalid = false, children, ...props },
  ref,
) {
  return (
    <select
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(
        "h-10 w-full rounded border bg-surface px-3 text-body text-ink",
        invalid ? "border-negative" : "border-border-strong",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
});
