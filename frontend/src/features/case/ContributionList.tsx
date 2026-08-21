import { cn } from "../../lib/cn";
import { formatNumber } from "../../lib/format";
import { FeatureNumber, type Contribution } from "./useCase";

function humanize(feature: string): string {
  return feature.replace(/_paise$/, "").replace(/_/g, " ");
}

function increasesRisk(c: Contribution): boolean {
  if (c.direction) return c.direction === "increases_risk";
  return c.contribution > 0;
}

/** The risk contributions: direction, magnitude and the actual feature value, each row a
 * click from its source in the drawer. This is where a PD stops being a verdict and becomes
 * a set of reasons a human can interrogate. */
export function ContributionList({ contributions }: { contributions: Contribution[] }) {
  const ranked = [...contributions].sort(
    (a, b) => Math.abs(b.contribution) - Math.abs(a.contribution),
  );
  const max = Math.max(1e-9, ...ranked.map((c) => Math.abs(c.contribution)));

  if (ranked.length === 0) {
    return <p className="text-sm text-muted">No contributions recorded.</p>;
  }

  return (
    <ul className="divide-y divide-border">
      {ranked.map((c) => {
        const up = increasesRisk(c);
        const width = `${Math.round((Math.abs(c.contribution) / max) * 100)}%`;
        return (
          <li key={c.feature} className="py-2">
            <FeatureNumber featureKey={c.feature} className="block w-full text-left">
              <div className="flex items-center justify-between gap-3">
                <span className="text-ink">{humanize(c.feature)}</span>
                <span
                  className={cn(
                    "text-xs font-medium",
                    up ? "text-negative" : "text-positive",
                  )}
                >
                  {up ? "↑ risk" : "↓ risk"}
                </span>
              </div>
              <div className="mt-1 flex items-center gap-2">
                <span className="h-1.5 flex-1 rounded-pill bg-sunken">
                  <span
                    className={cn("block h-1.5 rounded-pill", up ? "bg-negative" : "bg-positive")}
                    style={{ width }}
                  />
                </span>
                <span className="w-16 text-right text-xs tabular-nums text-muted">
                  {c.contribution >= 0 ? "+" : ""}
                  {formatNumber(c.contribution, 3)}
                </span>
                <span className="w-24 text-right text-xs tabular-nums text-muted">
                  {c.value !== null && c.value !== undefined ? formatNumber(c.value, 0) : "—"}
                </span>
              </div>
            </FeatureNumber>
          </li>
        );
      })}
    </ul>
  );
}
