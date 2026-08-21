import type { KeyboardEvent } from "react";

import { cn } from "../../lib/cn";
import type { Tone } from "../../components/ui/tones";
import { VIEW_LABELS, VIEW_ORDER } from "./useQueue";

export interface QueueViewTabsProps {
  /** Counts keyed by view; only the views the role can access are present. */
  counts: Record<string, number>;
  view: string;
  onViewChange: (view: string) => void;
}

/** The tone a non-zero count earns. A zero count always falls back to neutral so an
 * empty queue never wears an alarming colour. */
const ACTIVE_TONE: Record<string, Tone> = {
  "my-exceptions": "accent",
  "fraud-review": "negative",
  "evidence-needed": "caution",
  "newly-eligible": "positive",
  deterioration: "caution",
  "all-decisions": "muted",
  "qa-sample": "muted",
};

const COUNT_TONE_CLASS: Record<Tone, string> = {
  accent: "text-accent",
  positive: "text-positive",
  caution: "text-caution",
  negative: "text-negative",
  neutral: "text-ink",
  muted: "text-muted",
};

/**
 * The queue views, rendered as a summary layer that is also the switcher: one tile
 * per accessible view showing its live server count. A real tablist (roving
 * tabindex, arrow-key navigation). Views the role cannot access are absent (not in
 * `counts`). The count is printed once — on the tile you click.
 */
export function QueueViewTabs({ counts, view, onViewChange }: QueueViewTabsProps) {
  const views = VIEW_ORDER.filter((name) => name in counts);

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    const index = views.indexOf(view);
    const direction = event.key === "ArrowRight" ? 1 : -1;
    const next = views[(index + direction + views.length) % views.length];
    if (next) onViewChange(next);
  }

  return (
    <div
      role="tablist"
      aria-label="Queue views"
      onKeyDown={onKeyDown}
      className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6"
    >
      {views.map((name) => {
        const selected = name === view;
        const count = counts[name] ?? 0;
        const label = VIEW_LABELS[name] ?? name;
        const tone: Tone = count > 0 ? ACTIVE_TONE[name] ?? "neutral" : "neutral";
        return (
          <button
            key={name}
            role="tab"
            type="button"
            aria-selected={selected}
            aria-label={`${label} (${count})`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onViewChange(name)}
            className={cn(
              "flex flex-col items-start rounded border px-3 py-2 text-left transition-colors duration-fast",
              "focus:outline-none focus-visible:ring-2 focus-visible:ring-accent",
              selected
                ? "border-accent bg-accent-subtle"
                : "border-border bg-surface hover:border-border-strong hover:bg-surface-subtle",
            )}
          >
            <span
              className={cn(
                "text-heading font-semibold tabular-nums",
                selected ? "text-accent" : COUNT_TONE_CLASS[tone],
              )}
            >
              {count}
            </span>
            <span className="mt-0.5 text-sm font-medium text-ink">{label}</span>
          </button>
        );
      })}
    </div>
  );
}
