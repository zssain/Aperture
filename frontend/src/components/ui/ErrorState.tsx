import { cn } from "../../lib/cn";
import { Button } from "./Button";
import { Icon } from "./Icon";

export interface ErrorStateProps {
  title?: string;
  message: string;
  /** Shown in monospace so it can be quoted in a support request. The only
   * technical detail ever surfaced — never a stack trace or backend error class. */
  correlationId?: string;
  /** When provided, a Retry action is shown (only when retry is meaningful). */
  onRetry?: () => void;
  className?: string;
}

export function ErrorState({
  title = "Something went wrong",
  message,
  correlationId,
  onRetry,
  className,
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-start gap-3 rounded border border-border-strong bg-surface p-6",
        className,
      )}
    >
      <span className="flex h-9 w-9 items-center justify-center rounded-pill bg-caution-subtle text-caution">
        <Icon name="alert" size={18} />
      </span>
      <div className="space-y-1">
        <p className="text-heading font-semibold text-ink">{title}</p>
        <p className="text-sm text-muted">{message}</p>
        {correlationId ? (
          <p className="text-xs text-muted">
            Reference: <span className="font-mono text-neutral">{correlationId}</span>
          </p>
        ) : null}
      </div>
      {onRetry ? (
        <Button variant="secondary" size="sm" icon="replay" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </div>
  );
}
