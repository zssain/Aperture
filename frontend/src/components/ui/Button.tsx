import type { ButtonHTMLAttributes } from "react";
import { forwardRef } from "react";

import { cn } from "../../lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-surface border border-accent hover:opacity-90",
  secondary: "bg-surface text-ink border border-border-strong hover:bg-sunken",
  ghost: "bg-transparent text-ink border border-transparent hover:bg-sunken",
  danger: "bg-negative text-surface border border-negative hover:opacity-90",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-sm",
  md: "h-10 px-4 text-body",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", className, type, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type ?? "button"}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded font-medium",
        "transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...props}
    />
  );
});
