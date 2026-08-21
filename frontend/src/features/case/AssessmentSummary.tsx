import type { ReactNode } from "react";

import { InfoHint } from "../../components/ui/InfoHint";
import type { GlossaryKey } from "../../components/ui/glossary";
import { MetricValue } from "../../components/ui/MetricValue";
import type { Tone } from "../../components/ui/tones";
import { cn } from "../../lib/cn";
import { formatPaise } from "../../lib/format";
import type { Chips } from "./useCase";

const RAIL: Record<Tone, string> = {
  neutral: "bg-neutral",
  positive: "bg-positive",
  caution: "bg-caution",
  negative: "bg-negative",
  accent: "bg-accent",
  muted: "bg-border-strong",
};

interface TileProps {
  label: string;
  hint: GlossaryKey;
  tab: string;
  onSelect: (tab: string) => void;
  /** Tone paints the LEFT RAIL only — never the value. Four independent readings
   * must not be coloured as if they were one aggregate score. */
  tone: Tone;
  children: ReactNode;
}

/**
 * A summary tile. The whole tile navigates to its explaining tab; the InfoHint is a
 * sibling positioned over the corner (not nested inside the button) so there are no
 * nested interactive elements.
 */
function Tile({ label, hint, tab, onSelect, tone, children }: TileProps) {
  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => onSelect(tab)}
        className={cn(
          "relative w-full overflow-hidden rounded border border-border bg-surface p-4 pl-5 text-left",
          "transition-colors duration-fast hover:border-border-strong hover:bg-surface-subtle",
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-accent",
        )}
      >
        <span aria-hidden="true" className={cn("absolute inset-y-0 left-0 w-1", RAIL[tone])} />
        <span className="block text-sm text-muted">{label}</span>
        <span className="mt-1 block text-heading font-semibold text-ink">{children}</span>
      </button>
      <span className="absolute right-2 top-2 z-10">
        <InfoHint term={hint} />
      </span>
    </div>
  );
}

function affordabilityTone(status: string): Tone {
  if (status === "PASS") return "positive";
  if (status === "FAIL") return "negative";
  return "neutral";
}

function coverageTone(band: string | null, status: string): Tone {
  if (status !== "measured" || !band) return "neutral";
  if (band === "HIGH") return "positive";
  if (band === "LOW") return "caution";
  return "neutral";
}

function verificationTone(verification: string): Tone {
  if (verification === "CLEAR") return "positive";
  if (verification === "ELEVATED") return "caution";
  if (verification === "HIGH") return "negative";
  return "neutral";
}

/**
 * The four independent assessment readings under the decision: Risk, Affordability,
 * Evidence coverage and Verification. Each links to the tab that explains it.
 */
export function AssessmentSummary({
  chips,
  onSelectTab,
}: {
  chips: Chips;
  onSelectTab: (tab: string) => void;
}) {
  const pdPercent = chips.pd.value !== null ? chips.pd.value * 100 : null;

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {/* An uncalibrated PD keeps a neutral rail — never dressed up as certain. */}
      <Tile label="Risk (PD)" hint="pd" tab="assessment" onSelect={onSelectTab} tone="neutral">
        <MetricValue value={pdPercent} status={chips.pd.status} precision={1} unit="%" />
      </Tile>

      <Tile
        label="Affordability"
        hint="dsr"
        tab="assessment"
        onSelect={onSelectTab}
        tone={affordabilityTone(chips.affordability.status)}
      >
        <span className="inline-flex items-baseline gap-2">
          <span>{chips.affordability.status}</span>
          {chips.affordability.headroom_paise !== null ? (
            <span className="text-sm font-normal tabular-nums text-muted">
              {formatPaise(chips.affordability.headroom_paise)} headroom
            </span>
          ) : null}
        </span>
      </Tile>

      <Tile
        label="Evidence coverage"
        hint="evidence_coverage"
        tab="assessment"
        onSelect={onSelectTab}
        tone={coverageTone(chips.coverage.band, chips.coverage.status)}
      >
        <span className="inline-flex items-baseline gap-2">
          <MetricValue value={chips.coverage.score} status={chips.coverage.status} precision={0} />
          {chips.coverage.band ? (
            <span className="text-sm font-normal text-muted">{chips.coverage.band}</span>
          ) : null}
        </span>
      </Tile>

      <Tile
        label="Verification"
        hint="verification_status"
        tab="verification"
        onSelect={onSelectTab}
        tone={verificationTone(chips.verification)}
      >
        {chips.verification}
      </Tile>
    </div>
  );
}
