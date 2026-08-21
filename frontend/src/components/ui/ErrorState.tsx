import { cn } from "../../lib/cn";
import { Button } from "./Button";

export interface ErrorStateProps {
  title?: string;
  message: string;
  /** Shown in monospace so it can be quoted in a support request. */
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
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </div>
  );
}
