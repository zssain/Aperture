import { cn } from "../../lib/cn";
import { Chip } from "./Chip";

/**
 * The ONLY component permitted to render an assessment number. It is how invariant 8
 * is enforced in the UI:
 *   - measured        → the value, in ink.
 *   - uncalibrated    → the value in NEUTRAL grey with an `UNCAL` marker; never green.
 *   - unavailable     → an em-dash + muted label; never a fabricated 0.
 *   - insufficient_sample → an em-dash + "Insufficient sample" (with n if known).
 */
export type MetricStatus =
  | "measured"
  | "uncalibrated"
  | "unavailable"
  | "insufficient_sample";

export interface MetricValueProps {
  value: number | null;
  status: MetricStatus;
  unit?: string;
  precision?: number;
  sampleSize?: number;
  className?: string;
}

const EM_DASH = "—";

function formatValue(value: number, precision: number): string {
  return new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: precision,
    maximumFractionDigits: precision,
  }).format(value);
}

export function MetricValue({
  value,
  status,
  unit,
  precision = 0,
  sampleSize,
  className,
}: MetricValueProps) {
  if (status === "measured" && value !== null) {
    return (
      <span className={cn("tabular-nums text-ink", className)}>
        {formatValue(value, precision)}
        {unit ? <span className="text-muted"> {unit}</span> : null}
      </span>
    );
  }

  if (status === "uncalibrated" && value !== null) {
    return (
      <span
        className={cn("inline-flex items-center gap-2 tabular-nums text-neutral", className)}
      >
        <span>
          {formatValue(value, precision)}
          {unit ? <span className="text-muted"> {unit}</span> : null}
        </span>
        <Chip tone="neutral">UNCAL</Chip>
      </span>
    );
  }

  const label =
    status === "insufficient_sample"
      ? sampleSize !== undefined
        ? `Insufficient sample (n=${sampleSize})`
        : "Insufficient sample"
      : "Unavailable";

  return (
    <span className={cn("inline-flex items-center gap-2 text-neutral", className)}>
      <span aria-hidden="true" className="tabular-nums">
        {EM_DASH}
      </span>
      <span className="text-xs text-muted">{label}</span>
    </span>
  );
}
