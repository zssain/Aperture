import { MetricValue } from "../../components/ui/MetricValue";
import { formatPaise } from "../../lib/format";
import { FeatureNumber, type AffordabilityPayload } from "./useCase";

/** Affordability shown as a worked calculation, not a verdict — so the analyst sees where the
 * headroom comes from and can click any term through to its source. Money is money (invariant
 * 6); the DSR ratio is an assessment number and so goes through MetricValue. */
export function AffordabilityWorking({ payload }: { payload: AffordabilityPayload }) {
  const inflow = payload.net_monthly_income_paise;
  const headroom = payload.disposable_income_paise;
  const dsrPercent = payload.dsr !== null ? payload.dsr * 100 : null;

  return (
    <div className="space-y-3">
      <p className="text-sm leading-7 text-ink">
        <FeatureNumber featureKey="median_monthly_inflow_paise">
          Median monthly inflow {inflow !== null ? formatPaise(inflow) : "—"}
        </FeatureNumber>{" "}
        <span className="text-muted">−</span>{" "}
        <FeatureNumber featureKey="monthly_emi_paise">
          obligations {formatPaise(payload.recurring_obligations_paise)}
        </FeatureNumber>{" "}
        <span className="text-muted">−</span>{" "}
        <FeatureNumber featureKey="essential_expense_paise">
          essentials {formatPaise(payload.essential_expenses_paise)}
        </FeatureNumber>{" "}
        <span className="text-muted">=</span>{" "}
        <span className="font-medium tabular-nums text-ink">
          {headroom !== null ? formatPaise(headroom) : "—"} headroom
        </span>
      </p>
      <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted">
        <span>
          new EMI{" "}
          <span className="tabular-nums text-ink">
            {payload.new_emi_paise !== null ? formatPaise(payload.new_emi_paise) : "—"}
          </span>
        </span>
        <span className="inline-flex items-center gap-1">
          DSR{" "}
          <FeatureNumber featureKey="debt_service_ratio">
            <MetricValue
              value={dsrPercent}
              status={dsrPercent !== null ? "measured" : "unavailable"}
              precision={0}
              unit="%"
            />
          </FeatureNumber>
        </span>
        <span>
          status <span className="font-medium text-ink">{payload.status}</span>
        </span>
      </p>
    </div>
  );
}
