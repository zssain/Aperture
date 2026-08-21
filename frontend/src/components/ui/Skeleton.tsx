import { cn } from "../../lib/cn";

export interface SkeletonProps {
  /** Size via token utilities from the caller, e.g. "h-4 w-24". */
  className?: string;
}

export function Skeleton({ className }: SkeletonProps) {
  return (
    <span
      aria-hidden="true"
      className={cn("block animate-pulse rounded bg-border", className)}
    />
  );
}
