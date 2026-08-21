import type { ButtonHTMLAttributes } from "react";
import { forwardRef } from "react";

import { cn } from "../../lib/cn";
import { Icon, type IconName } from "./Icon";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  /** Optional leading icon. */
  icon?: IconName;
  /** Shows an inline spinner, sets aria-busy and blocks the click so a
   * consequential action cannot be double-submitted. */
  loading?: boolean;
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

/** A minimal ring spinner sized to the current text. */
function Spinner() {
  return (
    <span
      aria-hidden="true"
      className="inline-block h-4 w-4 animate-spin rounded-pill border-2 border-current border-r-transparent opacity-70"
    />
  );
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", icon, loading = false, className, type, disabled, onClick, children, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type ?? "button"}
      aria-busy={loading || undefined}
      disabled={disabled ?? loading}
      onClick={loading ? undefined : onClick}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded font-medium",
        "transition-colors duration-fast disabled:cursor-not-allowed disabled:opacity-50",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...props}
    >
      {loading ? <Spinner /> : icon ? <Icon name={icon} size={size === "sm" ? 16 : 18} /> : null}
      {children}
    </button>
  );
});

export interface IconButtonProps extends Omit<ButtonProps, "icon" | "children"> {
  icon: IconName;
  /** Required — an icon-only control must have an accessible name. */
  label: string;
}

/** An icon-only button that forces an accessible label. */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  function IconButton({ icon, label, size = "md", className, ...props }, ref) {
    return (
      <Button
        ref={ref}
        size={size}
        aria-label={label}
        className={cn(size === "sm" ? "w-8 px-0" : "w-10 px-0", className)}
        {...props}
      >
        <Icon name={icon} size={size === "sm" ? 16 : 18} />
      </Button>
    );
  },
);
