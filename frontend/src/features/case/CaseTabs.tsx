import { Tabs } from "../../components/ui/Tabs";
import { TAB_LABELS, TABS } from "./useCase";

/** The case tabs. Wraps the shared Tabs primitive (roving tabindex + arrow-key navigation);
 * the active tab is controlled by the page from the URL and defaults to blocking_tab. */
export function CaseTabs({
  active,
  onSelect,
}: {
  active: string;
  onSelect: (tab: string) => void;
}) {
  const items = TABS.map((tab) => ({ value: tab, label: TAB_LABELS[tab] ?? tab }));
  return <><label className="block text-sm md:hidden">Case section<select className="mt-1 h-10 w-full rounded border border-border-strong bg-surface px-3" value={active} onChange={(event) => onSelect(event.target.value)}>{items.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label><Tabs className="hidden md:flex" items={items} value={active} onValueChange={onSelect} ariaLabel="Case sections" /></>;
}
