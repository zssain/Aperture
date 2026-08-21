import * as RadixPopover from "@radix-ui/react-popover";

import { cn } from "../../lib/cn";
import { GLOSSARY, type GlossaryKey } from "./glossary";
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
  const entry = GLOSSARY[term];
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
          className="z-50 w-72 max-w-screen-safe animate-sheet-in rounded border border-border bg-surface p-3 shadow-drawer"
        >
          <p className="text-sm font-semibold text-ink">{entry.term}</p>
          <p className="mt-1 text-sm text-muted">{entry.definition}</p>
          <RadixPopover.Arrow className="fill-surface" />
        </RadixPopover.Content>
      </RadixPopover.Portal>
    </RadixPopover.Root>
  );
}
