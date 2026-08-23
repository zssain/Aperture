import * as RadixPopover from "@radix-ui/react-popover";

import { cn } from "../../lib/cn";
import { GLOSSARY, type GlossaryEntry, type GlossaryKey } from "./glossary";
import { Icon } from "./Icon";

export interface InfoHintProps {
  /** Which glossary entry to show. */
  term: GlossaryKey;
  className?: string;
}

/** A small "?" affordance that opens a glossary definition. Click/Enter/Space
 * activated (via a real button) rather than hover-only, so it is keyboard- and
 * touch-reachable. */
export function InfoHint({ term, className }: InfoHintProps) {
  const entry: GlossaryEntry = GLOSSARY[term];
  return (
    <RadixPopover.Root>
      <RadixPopover.Trigger asChild>
        <button
          type="button"
          aria-label={`What is ${entry.term}?`}
          className={cn(
            "inline-flex h-4 w-4 items-center justify-center rounded-pill border border-border-strong text-muted transition-colors duration-fast hover:border-accent hover:text-accent",
            className,
          )}
        >
          <Icon name="info" size={12} />
        </button>
      </RadixPopover.Trigger>
      <RadixPopover.Portal>
        <RadixPopover.Content
          align="start"
          sideOffset={6}
          collisionPadding={12}
          className="z-50 max-h-overlay w-80 max-w-screen-safe animate-sheet-in overflow-y-auto rounded border border-border bg-surface p-4 shadow-drawer"
        >
          <p className="text-sm font-semibold text-ink">{entry.term}</p>
          <p className="mt-1.5 text-sm leading-relaxed text-muted">{entry.definition}</p>

          {entry.howCalculated ? (
            <div className="mt-3 border-t border-border pt-3">
              <p className="eyebrow text-accent">How it&rsquo;s calculated</p>
              <p className="mt-1.5 text-sm leading-relaxed text-muted">{entry.howCalculated}</p>
            </div>
          ) : null}

          {entry.formula ? (
            <div className="mt-3">
              <p className="eyebrow text-muted">Formula</p>
              <p className="mt-1.5 rounded border border-border bg-sunken px-2.5 py-2 font-mono text-xs leading-relaxed text-ink">
                {entry.formula}
              </p>
            </div>
          ) : null}

          {entry.note ? (
            <div className="mt-3 flex gap-2 rounded border border-border bg-accent-subtle px-2.5 py-2">
              <span aria-hidden="true" className="mt-px shrink-0 text-accent">
                <Icon name="info" size={14} />
              </span>
              <p className="text-xs leading-relaxed text-ink">{entry.note}</p>
            </div>
          ) : null}

          <RadixPopover.Arrow className="fill-surface" />
        </RadixPopover.Content>
      </RadixPopover.Portal>
    </RadixPopover.Root>
  );
}
