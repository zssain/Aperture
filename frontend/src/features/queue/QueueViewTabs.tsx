import { Tabs } from "../../components/ui/Tabs";
import { VIEW_LABELS, VIEW_ORDER } from "./useQueue";

export interface QueueViewTabsProps {
  /** Counts keyed by view; only the views the role can access are present. */
  counts: Record<string, number>;
  view: string;
  onViewChange: (view: string) => void;
}

/** The view tabs, each carrying its own count — a count is only useful attached to the
 * thing you click. Views the role cannot access are absent (they are not in ``counts``). */
export function QueueViewTabs({ counts, view, onViewChange }: QueueViewTabsProps) {
  const items = VIEW_ORDER.filter((name) => name in counts).map((name) => ({
    value: name,
    label: `${VIEW_LABELS[name] ?? name} (${counts[name] ?? 0})`,
  }));

  return (
    <Tabs
      items={items}
      value={view}
      onValueChange={onViewChange}
      ariaLabel="Queue views"
    />
  );
}
