import { MetricValue } from "../../components/ui/MetricValue";
import { formatPercent } from "../../lib/format";
import type { CoveragePayload } from "./useCase";

/** Coverage as a component breakdown: what each component contributed, and what each missing
 * source could still add — so "coverage 41" is a set of gaps a human can act on, not a grade. */
export function CoverageBreakdown({ payload }: { payload: CoveragePayload }) {
  return (
    <div className="space-y-4">
      <div className="flex items-baseline gap-2">
        <MetricValue value={payload.score} status="measured" precision={0} />
        <span className="text-sm text-muted">/ 100 · {payload.band}</span>
      </div>

      <div>
        <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">Components</h3>
        <ul className="divide-y divide-border">
          {payload.components.map((component) => (
            <li key={component.name} className="flex items-center justify-between gap-3 py-1.5">
              <span className="text-ink">{component.name.replace(/_/g, " ")}</span>
              <span className="text-xs text-muted">{component.detail}</span>
              <span className="w-24 text-right tabular-nums text-ink">
                +{formatPercent(component.contribution / 100, 0)}
              </span>
            </li>
          ))}
        </ul>
      </div>

      {payload.missing_sources.length > 0 ? (
        <div>
          <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">
            Missing sources
          </h3>
          <ul className="divide-y divide-border">
            {payload.missing_sources.map((missing) => (
              <li
                key={missing.source_type}
                className="flex items-center justify-between gap-3 py-1.5"
              >
                <span className="text-ink">{missing.source_type}</span>
                <span className="text-xs text-muted">{missing.why}</span>
                <span className="w-24 text-right tabular-nums text-positive">
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
