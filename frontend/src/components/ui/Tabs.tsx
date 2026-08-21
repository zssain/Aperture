import type { KeyboardEvent } from "react";

import { cn } from "../../lib/cn";

export interface TabItem {
  value: string;
  label: string;
  /** Optional count shown alongside the label. */
  count?: number;
}

export type TabsVariant = "underline" | "segmented";

export interface TabsProps {
  items: TabItem[];
  value: string;
  onValueChange: (value: string) => void;
  ariaLabel: string;
  variant?: TabsVariant;
  className?: string;
}

/** Accessible tablist (roving tabindex, arrow-key navigation). Not an overlay, so
 * built with semantic elements rather than a library. */
export function Tabs({
  items,
  value,
  onValueChange,
  ariaLabel,
  variant = "underline",
  className,
}: TabsProps) {
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    const index = items.findIndex((tab) => tab.value === value);
    const direction = event.key === "ArrowRight" ? 1 : -1;
    const next = items[(index + direction + items.length) % items.length];
    if (next) onValueChange(next.value);
  }

  const segmented = variant === "segmented";

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      onKeyDown={onKeyDown}
      className={cn(
        segmented
          ? "inline-flex gap-1 rounded bg-sunken p-1"
          : "flex gap-1 border-b border-border",
        className,
      )}
    >
      {items.map((tab) => {
        const selected = tab.value === value;
        return (
          <button
            key={tab.value}
            role="tab"
            type="button"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onValueChange(tab.value)}
            className={cn(
              "inline-flex items-center gap-2 text-sm font-medium transition-colors duration-menu",
              segmented
                ? cn(
                    "h-8 rounded px-3",
                    selected
                      ? "bg-surface text-ink border border-border-strong"
                      : "border border-transparent text-muted hover:text-ink",
                  )
                : cn(
                    "-mb-px h-10 border-b-2 px-4",
                    selected
                      ? "border-accent text-accent"
                      : "border-transparent text-muted hover:text-ink",
                  ),
            )}
          >
            <span>{tab.label}</span>
            {typeof tab.count === "number" ? (
              <span
                className={cn(
                  "rounded-pill px-1.5 text-xs font-medium tabular-nums",
                  selected ? "bg-accent-subtle text-accent" : "bg-sunken text-muted",
                )}
              >
                {tab.count}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
