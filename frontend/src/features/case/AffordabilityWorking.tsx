import type { ReactNode } from "react";

import { Badge } from "../../components/ui/Badge";
import { MetricValue } from "../../components/ui/MetricValue";
import type { Tone } from "../../components/ui/tones";
import { cn } from "../../lib/cn";
import { formatPaise } from "../../lib/format";
import { FeatureNumber, type AffordabilityPayload } from "./useCase";

interface LineProps {
  label: ReactNode;
  /** "+" for an inflow, "−" for a deduction, "=" for a subtotal. */
  op?: "+" | "−" | "=";
  children: ReactNode;
  /** A subtotal line gets a top rule and heavier weight. */
  rule?: boolean;
  strong?: boolean;
}

/** One line of the ledger: operator, label, right-aligned amount. */
function Line({ label, op, children, rule, strong }: LineProps) {
  return (
    <div
      className={cn(
        "flex items-baseline justify-between gap-4 py-1.5 text-sm",
        rule && "border-t border-border-strong pt-2",
      )}
    >
      <span className={cn(strong ? "font-medium text-ink" : "text-muted")}>{label}</span>
      <span className="inline-flex items-baseline gap-1.5">
        {op ? <span className="w-3 text-right text-muted">{op}</span> : null}
        <span
          className={cn(
            "w-32 text-right tabular-nums",
            strong ? "font-semibold text-ink" : "text-ink",
          )}
        >
          {children}
        </span>
      </span>
    </div>
  );
}

const STATUS_TONE: Record<string, Tone> = {
  PASS: "positive",
  FAIL: "negative",
};

const money = (paise: number | null): string => (paise !== null ? formatPaise(paise) : "—");

/** Affordability as a worked ledger, not a sentence — the analyst sees where the
 * headroom comes from and can click any term through to its source. Money is money
 * (invariant 6); the DSR ratio is an assessment number and goes through MetricValue.
 * The underlying formula is unchanged. */
export function AffordabilityWorking({ payload }: { payload: AffordabilityPayload }) {
  const dsrPercent = payload.dsr !== null ? payload.dsr * 100 : null;
  const ceilingPercent = payload.dsr_ceiling * 100;

  return (
    <div className="space-y-4">
      <div className="rounded border border-border">
        <div className="px-3">
          <Line
            label={
              <FeatureNumber featureKey="median_monthly_inflow_paise">
                Monthly inflow
              </FeatureNumber>
            }
            op="+"
          >
            {money(payload.net_monthly_income_paise)}
          </Line>
          <Line
            label={
              <FeatureNumber featureKey="essential_expense_paise">
                Essential expenses
              </FeatureNumber>
            }
            op="−"
          >
            {money(payload.essential_expenses_paise)}
          </Line>
          <Line
            label={
              <FeatureNumber featureKey="monthly_emi_paise">
                Existing obligations
              </FeatureNumber>
            }
            op="−"
          >
            {money(payload.recurring_obligations_paise)}
          </Line>
          <Line label="Available headroom" op="=" rule strong>
            {money(payload.disposable_income_paise)}
          </Line>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-sm">
          <span className="text-muted">
            Proposed EMI{" "}
            <span className="ml-1 tabular-nums text-ink">{money(payload.new_emi_paise)}</span>
          </span>
          <span className="inline-flex items-center gap-1.5 text-muted">
            DSR{" "}
            <FeatureNumber featureKey="debt_service_ratio" className="tabular-nums text-ink">
              <MetricValue
                value={dsrPercent}
                status={dsrPercent !== null ? "measured" : "unavailable"}
                precision={0}
                unit="%"
              />
            </FeatureNumber>
            <span className="text-xs text-muted">/ {ceilingPercent.toFixed(0)}% ceiling</span>
          </span>
        </div>
        <Badge tone={STATUS_TONE[payload.status] ?? "neutral"} glyph>
          {payload.status}
        </Badge>
      </div>
    </div>
  );
}
