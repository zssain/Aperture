import { Icon } from "../../components/ui/Icon";
import { cn } from "../../lib/cn";
import { formatNumber, formatPaise } from "../../lib/format";
import { featureLabel } from "./labels";
import { FeatureNumber, type Contribution } from "./useCase";

/** Money features are stored in paise → show as ₹; ratios keep two decimals; whole
 * counts drop the trailing zeros. Missing stays an em-dash, never a zero. */
function formatFeatureValue(key: string, value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (key.endsWith("_paise")) return formatPaise(value);
  return formatNumber(value, Number.isInteger(value) ? 0 : 2);
}

function increasesRisk(c: Contribution): boolean {
  if (c.direction) return c.direction === "increases_risk";
  return c.contribution > 0;
}

/**
 * The risk contributions on a bidirectional scale: factors that LOWER risk sit left
 * of the centre line, factors that RAISE it sit right. Direction is carried by
 * position, an icon AND a word — never colour alone. Each row is a click through to
 * its source in the evidence drawer, and the feature name stays the button's
 * accessible text.
 */
export function ContributionList({ contributions }: { contributions: Contribution[] }) {
  const ranked = [...contributions].sort(
    (a, b) => Math.abs(b.contribution) - Math.abs(a.contribution),
  );
  const max = Math.max(1e-9, ...ranked.map((c) => Math.abs(c.contribution)));

  if (ranked.length === 0) {
    return <p className="text-sm text-muted">No contributions recorded.</p>;
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-eyebrow font-semibold uppercase text-muted">
        <span className="inline-flex items-center gap-1">
          <Icon name="chevron-left" size={12} /> Lowers risk
        </span>
        <span className="inline-flex items-center gap-1">
          Raises risk <Icon name="chevron-right" size={12} />
        </span>
      </div>
      <ul className="divide-y divide-border">
        {ranked.map((c) => {
          const up = increasesRisk(c);
          const half = `${Math.round((Math.abs(c.contribution) / max) * 50)}%`;
          return (
            <li key={c.feature} className="py-2">
              <FeatureNumber featureKey={c.feature} className="block w-full text-left">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-ink">{featureLabel(c.feature)}</span>
                  <span
                    className={cn(
                      "inline-flex items-center gap-1 text-xs font-medium",
                      up ? "text-negative" : "text-positive",
                    )}
                  >
                    <Icon name={up ? "chevron-up" : "chevron-down"} size={13} />
                    {up ? "Higher risk" : "Lower risk"}
                  </span>
                </div>
                <div className="mt-1.5 flex items-center gap-3">
                  {/* Bidirectional track: bar grows from the centre line. */}
                  <span className="relative h-2 flex-1 rounded-pill bg-sunken">
                    <span
                      aria-hidden="true"
                      className="absolute left-1/2 top-0 h-2 w-px -translate-x-1/2 bg-border-strong"
                    />
                    <span
                      className={cn(
                        "absolute top-0 h-2",
                        up
                          ? "left-1/2 rounded-r-pill bg-negative"
                          : "right-1/2 rounded-l-pill bg-positive",
                      )}
                      style={{ width: half }}
                    />
                  </span>
                  <span className="w-16 text-right text-xs tabular-nums text-muted">
                    {c.contribution >= 0 ? "+" : ""}
                    {formatNumber(c.contribution, 3)}
                  </span>
                  <span className="w-24 text-right text-xs tabular-nums text-muted">
                    {formatFeatureValue(c.feature, c.value)}
                  </span>
                </div>
              </FeatureNumber>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
