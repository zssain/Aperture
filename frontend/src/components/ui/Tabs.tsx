import type { KeyboardEvent } from "react";

import { cn } from "../../lib/cn";

export interface TabItem {
  value: string;
  label: string;
}

export interface TabsProps {
  items: TabItem[];
  value: string;
  onValueChange: (value: string) => void;
  ariaLabel: string;
  className?: string;
}

/** Accessible tablist (roving tabindex, arrow-key navigation). Not an overlay, so
 * built with semantic elements rather than a library. */
export function Tabs({ items, value, onValueChange, ariaLabel, className }: TabsProps) {
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    const index = items.findIndex((tab) => tab.value === value);
    const direction = event.key === "ArrowRight" ? 1 : -1;
    const next = items[(index + direction + items.length) % items.length];
    if (next) onValueChange(next.value);
  }

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      onKeyDown={onKeyDown}
      className={cn("flex gap-1 border-b border-border", className)}
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
              "-mb-px h-10 border-b-2 px-4 text-sm font-medium",
              selected
                ? "border-accent text-accent"
                : "border-transparent text-muted hover:text-ink",
            )}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
