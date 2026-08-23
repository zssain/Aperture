import { Button } from "../../components/ui/Button";
import { Chip } from "../../components/ui/Chip";
import { Icon } from "../../components/ui/Icon";

interface ImportSummaryProps {
  ingested: number;
  deduplicated: number;
  sourceLabel: string;
  tierLabel: string;
  decisionReady: boolean;
  onOpenCase: () => void;
}

/** The landing moment after ingestion: what was imported, from where, at what
 * evidence tier — every number comes from the real ingestion accounting. */
export function ImportSummary({
  ingested,
  deduplicated,
  sourceLabel,
  tierLabel,
  decisionReady,
  onOpenCase,
}: ImportSummaryProps) {
  return (
    <section
      role="status"
      aria-labelledby="import-summary-heading"
      className="rounded border border-positive bg-positive-subtle p-5"
    >
      <div className="flex flex-wrap items-center gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-pill bg-positive text-surface">
          <Icon name="check" size={18} />
        </span>
        <div className="min-w-0 flex-1">
          <h2 id="import-summary-heading" className="text-heading font-semibold text-ink">
            {ingested.toLocaleString("en-IN")} transaction{ingested === 1 ? "" : "s"} imported
          </h2>
          <p className="mt-0.5 text-sm text-muted">
            {sourceLabel}
            {deduplicated > 0 ? ` · ${deduplicated} duplicate${deduplicated === 1 ? "" : "s"} skipped` : ""}
          </p>
        </div>
        <Chip tone="positive">{tierLabel}</Chip>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button size="sm" onClick={onOpenCase}>
          Open case file
        </Button>
        <p className="text-sm text-muted">
          {decisionReady
            ? "Decision recorded — opening the case in a moment…"
            : "The case will open when the decision lands."}
        </p>
      </div>
    </section>
  );
}
