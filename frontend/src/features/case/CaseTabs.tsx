import { Select } from "../../components/ui/Select";
import { Tabs } from "../../components/ui/Tabs";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { TAB_LABELS, TABS } from "./useCase";

/** The case tabs. Wraps the shared Tabs primitive (roving tabindex + arrow-key
 * navigation) on desktop and collapses to a native select below md. Exactly one is
 * mounted (never both) so a screen reader hears one control; defaults to the desktop
 * tablist when matchMedia is unavailable (jsdom). */
export function CaseTabs({
  active,
  onSelect,
}: {
  active: string;
  onSelect: (tab: string) => void;
}) {
  const items = TABS.map((tab) => ({ value: tab, label: TAB_LABELS[tab] ?? tab }));
  const isDesktop = useMediaQuery("(min-width: 768px)", true);

  if (!isDesktop) {
    return (
      <Select
        aria-label="Case section"
        value={active}
        onChange={(event) => onSelect(event.target.value)}
      >
        {items.map((item) => (
          <option key={item.value} value={item.value}>
            {item.label}
          </option>
        ))}
      </Select>
    );
  }

  return (
    <Tabs
      items={items}
      value={active}
      onValueChange={onSelect}
      ariaLabel="Case sections"
    />
  );
}
