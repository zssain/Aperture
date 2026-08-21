import type { InputHTMLAttributes } from "react";
import { forwardRef } from "react";

import { cn } from "../../lib/cn";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, invalid = false, ...props },
  ref,
) {
  return (
    <input
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(
        "h-10 w-full rounded border bg-surface px-3 text-body text-ink",
        "placeholder:text-muted",
        invalid ? "border-negative" : "border-border-strong",
        className,
      )}
      {...props}
    />
  );
});
