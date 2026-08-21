import * as Dialog from "@radix-ui/react-dialog";
import type { ReactNode } from "react";

import { cn } from "../../lib/cn";

export interface ModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  trigger?: ReactNode;
}

/** Centred modal dialog (Radix Dialog): focus trapped, focus returned on close. */
export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  trigger,
}: ModalProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      {trigger ? <Dialog.Trigger asChild>{trigger}</Dialog.Trigger> : null}
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/20" />
        <Dialog.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-50 w-drawer max-w-full -translate-x-1/2 -translate-y-1/2",
            "rounded border border-border bg-surface shadow-modal",
          )}
        >
          <div className="border-b border-border p-4">
            <Dialog.Title className="text-heading font-semibold text-ink">
              {title}
            </Dialog.Title>
            {description ? (
              <Dialog.Description className="text-sm text-muted">
                {description}
              </Dialog.Description>
            ) : null}
          </div>
          <div className="p-4">{children}</div>
          {footer ? (
            <div className="flex justify-end gap-2 border-t border-border p-4">
              {footer}
            </div>
          ) : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
