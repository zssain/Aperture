import { Badge } from "../../components/ui/Badge";
import type { QueueChange } from "./useQueue";

export function ChangeBadge({ change }: { change: QueueChange }) {
  const tone = change.direction === "IMPROVED" ? "positive" : change.direction === "WORSENED" ? "negative" : "neutral";
  const spoken = change.direction === "IMPROVED" ? "Improved" : change.direction === "WORSENED" ? "Deteriorated" : "Unchanged";
  return (
    <Badge tone={tone} className="mt-1">
      <span className="sr-only">{spoken} decision: </span>
      {change.previous_band} → {change.new_band}
    </Badge>
  );
}
