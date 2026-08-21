import * as RadixPopover from "@radix-ui/react-popover";
import type { ReactNode } from "react";

import { cn } from "../../lib/cn";

export interface PopoverProps {
  trigger: ReactNode;
  children: ReactNode;
  align?: "start" | "center" | "end";
  className?: string;
}

/** Overlay popover (Radix). Used for the user menu and small contextual panels. */
export function Popover({ trigger, children, align = "end", className }: PopoverProps) {
  return (
    <RadixPopover.Root>
      <RadixPopover.Trigger asChild>{trigger}</RadixPopover.Trigger>
      <RadixPopover.Portal>
        <RadixPopover.Content
          align={align}
          sideOffset={6}
          className={cn(
            "z-50 min-w-menu rounded border border-border bg-surface shadow-drawer",
            className,
          )}
        >
          {children}
        </RadixPopover.Content>
      </RadixPopover.Portal>
    </RadixPopover.Root>
  );
}
