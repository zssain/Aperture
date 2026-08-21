import * as Dialog from "@radix-ui/react-dialog";
import type { ReactNode } from "react";

import { cn } from "../../lib/cn";
import { Icon } from "./Icon";

type ModalSize = "sm" | "md" | "lg";
type ModalTone = "default" | "warning";

export interface ModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  trigger?: ReactNode;
  size?: ModalSize;
  /** "warning" tints the header for consequential dialogs. */
  tone?: ModalTone;
}

const SIZES: Record<ModalSize, string> = {
  sm: "w-modal-sm",
  md: "w-drawer",
  lg: "w-modal-lg",
};

/** Centred modal dialog (Radix Dialog): focus trapped, focus returned on close.
 * The body scrolls independently so a long dialog never pushes its footer off
 * screen; header and footer stay pinned. */
export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  trigger,
  size = "md",
  tone = "default",
}: ModalProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      {trigger ? <Dialog.Trigger asChild>{trigger}</Dialog.Trigger> : null}
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/30 animate-fade-in" />
        <Dialog.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-50 flex max-h-overlay max-w-screen-safe -translate-x-1/2 -translate-y-1/2 flex-col",
            "animate-modal-in rounded border border-border bg-surface shadow-modal",
            SIZES[size],
          )}
        >
          <div
            className={cn(
              "flex items-start justify-between gap-4 border-b p-4",
              tone === "warning"
                ? "border-caution/30 bg-caution-subtle"
                : "border-border",
            )}
          >
            <div className="min-w-0 space-y-0.5">
              <Dialog.Title
                className={cn(
                  "flex items-center gap-2 text-heading font-semibold",
                  tone === "warning" ? "text-caution" : "text-ink",
                )}
              >
                {tone === "warning" ? <Icon name="alert" size={18} /> : null}
                {title}
              </Dialog.Title>
              {description ? (
                <Dialog.Description className="text-sm text-muted">
                  {description}
                </Dialog.Description>
              ) : null}
            </div>
            <Dialog.Close
              aria-label="Close dialog"
              className="-mr-1 -mt-1 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded text-muted transition-colors duration-fast hover:bg-sunken hover:text-ink"
            >
              <Icon name="close" size={18} />
            </Dialog.Close>
          </div>
          <div className="scrollbar-slim overflow-y-auto p-4">{children}</div>
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
