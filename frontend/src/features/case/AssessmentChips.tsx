import type { ReactNode } from "react";

import { MetricValue } from "../../components/ui/MetricValue";
import { cn } from "../../lib/cn";
import { formatPaise } from "../../lib/format";
import type { Chips } from "./useCase";

interface ChipLinkProps {
  label: string;
  tab: string;
  onSelect: (tab: string) => void;
  children: ReactNode;
}

function ChipLink({ label, tab, onSelect, children }: ChipLinkProps) {
  return (
    <button
      type="button"
      onClick={() => onSelect(tab)}
      className={cn(
        "inline-flex items-center gap-2 rounded-pill border border-border-strong bg-surface",
        "px-3 py-1 text-sm hover:bg-sunken focus:outline-none focus-visible:ring-2 focus-visible:ring-accent",
      )}
    >
      <span className="text-muted">{label}</span>
      {children}
    </button>
  );
}

/** The four assessment chips under the decision band, each a link to its tab. Every
 * assessment number is a MetricValue so an uncalibrated PD renders neutral/UNCAL here exactly
 * as it does inside the Assessment tab. */
export function AssessmentChips({
  chips,
  onSelectTab,
}: {
  chips: Chips;
  onSelectTab: (tab: string) => void;
}) {
  const pdPercent = chips.pd.value !== null ? chips.pd.value * 100 : null;
  return (
    <div className="flex flex-wrap gap-2">
      <ChipLink label="PD" tab="assessment" onSelect={onSelectTab}>
        <MetricValue value={pdPercent} status={chips.pd.status} precision={1} unit="%" />
      </ChipLink>

      <ChipLink label="Coverage" tab="assessment" onSelect={onSelectTab}>
        <MetricValue value={chips.coverage.score} status={chips.coverage.status} precision={0} />
        {chips.coverage.band ? <span className="text-ink">{chips.coverage.band}</span> : null}
      </ChipLink>

      <ChipLink label="Afford" tab="assessment" onSelect={onSelectTab}>
        <span className="text-ink">{chips.affordability.status}</span>
        {chips.affordability.headroom_paise !== null ? (
          <span className="tabular-nums text-ink">
            {formatPaise(chips.affordability.headroom_paise)}
          </span>
        ) : null}
      </ChipLink>

      <ChipLink label="Verify" tab="verification" onSelect={onSelectTab}>
        <span className="text-ink">{chips.verification}</span>
      </ChipLink>
    </div>
  );
}
