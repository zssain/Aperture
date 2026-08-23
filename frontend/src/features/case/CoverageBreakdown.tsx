import { MetricValue } from "../../components/ui/MetricValue";
import { formatPercent } from "../../lib/format";
import { coverageComponentLabel, sourceTypeLabel } from "./labels";
import type { CoveragePayload } from "./useCase";

/** Coverage as a component breakdown: what each component contributed, and what each
 * missing source could still add — so "coverage 41" is a set of gaps a human can act
 * on, not a grade. This measures how COMPLETE the evidence file is, not how
 * creditworthy the applicant is. */
export function CoverageBreakdown({ payload }: { payload: CoveragePayload }) {
  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-baseline gap-2">
          <span className="text-title font-semibold text-ink">
            <MetricValue value={payload.score} status="measured" precision={0} />
          </span>
          <span className="text-sm text-muted">/ 100 · {payload.band} confidence</span>
        </div>
        <p className="mt-1 text-xs text-muted">
          Completeness of the evidence file — not a measure of creditworthiness.
        </p>
      </div>

      <div>
        <h3 className="mb-1 eyebrow">Contributing components</h3>
        <ul className="divide-y divide-border">
          {payload.components.map((component) => (
            <li key={component.name} className="flex items-center justify-between gap-3 py-1.5">
              <span className="text-ink">{coverageComponentLabel(component.name)}</span>
              <span className="flex-1 text-right text-xs text-muted">{component.detail}</span>
              <span className="w-16 text-right tabular-nums text-ink">
                +{formatPercent(component.contribution / 100, 0)}
              </span>
            </li>
          ))}
        </ul>
      </div>

      {payload.missing_sources.length > 0 ? (
        <div>
          <h3 className="mb-1 eyebrow">Missing sources — what each would add</h3>
          <ul className="divide-y divide-border">
            {payload.missing_sources.map((missing) => (
              <li
                key={missing.source_type}
                className="flex items-center justify-between gap-3 py-1.5"
              >
                <span className="text-ink">{sourceTypeLabel(missing.source_type)}</span>
                <span className="flex-1 text-right text-xs text-muted">{missing.why}</span>
                <span className="w-16 text-right tabular-nums text-positive">
                  +{missing.coverage_delta}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
