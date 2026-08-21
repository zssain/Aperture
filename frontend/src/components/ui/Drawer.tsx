import * as Dialog from "@radix-ui/react-dialog";
import type { ReactNode } from "react";

import { cn } from "../../lib/cn";

export interface DrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
  trigger?: ReactNode;
}

/** Right-side, 480px drawer (Radix Dialog): focus trapped, focus returned to the
 * trigger on close, light non-blocking scrim. */
export function Drawer({
  open,
  onOpenChange,
  title,
  description,
  children,
  trigger,
}: DrawerProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      {trigger ? <Dialog.Trigger asChild>{trigger}</Dialog.Trigger> : null}
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/10" />
        <Dialog.Content
          className={cn(
            "fixed right-0 top-0 z-50 flex h-full w-drawer flex-col",
            "border-l border-border bg-surface shadow-drawer",
          )}
        >
          <div className="flex items-start justify-between border-b border-border p-4">
            <div className="space-y-1">
              <Dialog.Title className="text-heading font-semibold text-ink">
                {title}
              </Dialog.Title>
              {description ? (
                <Dialog.Description className="text-sm text-muted">
                  {description}
                </Dialog.Description>
              ) : null}
            </div>
            <Dialog.Close
              aria-label="Close"
              className="rounded px-2 py-1 text-sm text-muted hover:bg-sunken"
            >
              Close
            </Dialog.Close>
          </div>
          <div className="flex-1 overflow-auto p-4">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
