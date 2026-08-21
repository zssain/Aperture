import { cn } from "../../lib/cn";

export interface SkeletonProps {
  /** Size via token utilities from the caller, e.g. "h-4 w-24". */
  className?: string;
}

export function Skeleton({ className }: SkeletonProps) {
  return (
    <span
      aria-hidden="true"
      className={cn("block rounded shimmer", className)}
    />
  );
}

export interface SkeletonTextProps {
  /** Number of lines to render. */
  lines?: number;
  className?: string;
}

/** A stack of skeleton lines; the last line is shortened to read as text. */
export function SkeletonText({ lines = 3, className }: SkeletonTextProps) {
  return (
    <span className={cn("block space-y-2", className)} aria-hidden="true">
      {Array.from({ length: lines }).map((_, index) => (
        <span
          key={index}
          className={cn(
            "block h-4 rounded shimmer",
            index === lines - 1 ? "w-2/3" : "w-full",
          )}
        />
      ))}
    </span>
  );
}
