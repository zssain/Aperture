import { MetricValue } from "../../../components/ui/MetricValue";
import { AffordabilityWorking } from "../AffordabilityWorking";
import { ContributionList } from "../ContributionList";
import { CoverageBreakdown } from "../CoverageBreakdown";
import type {
  AffordabilityPayload,
  CaseData,
  CoveragePayload,
  RiskPayload,
} from "../useCase";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section aria-label={title} className="space-y-3">
      <h2 className="text-sm font-medium text-ink">{title}</h2>
      {children}
    </section>
  );
}

/** Assessment tab: PD (via MetricValue, with model + calibration in mono), the contributions,
 * the worked affordability calculation, and the coverage breakdown. */
export function AssessmentTab({ data }: { data: CaseData }) {
  const risk = data.assessments.RISK;
  const coverage = data.assessments.COVERAGE;
  const afford = data.assessments.AFFORDABILITY;

  if (!risk || !coverage || !afford) {
    return (
      <p className="text-sm text-negative">
        One or more assessments were unavailable — there is no decision to explain.
      </p>
    );
  }

  const riskPayload = risk.payload as unknown as RiskPayload;
  const coveragePayload = coverage.payload as unknown as CoveragePayload;
  const affordPayload = afford.payload as unknown as AffordabilityPayload;

  const pd = riskPayload.pd;
  const pdStatus = data.chips.pd.status;

  return (
    <div data-testid="case-tab-body" className="space-y-8 case-wide:grid case-wide:grid-cols-2 case-wide:gap-8 case-wide:space-y-0">
      <Section title="Probability of default">
        <div className="flex items-baseline gap-3">
          <span className="text-[24px] font-semibold">
            <MetricValue
              value={pd !== null ? pd * 100 : null}
              status={pdStatus}
              precision={1}
              unit="%"
            />
          </span>
          <span className="font-mono text-xs text-muted">
            {risk.model_version ?? "model —"} · {risk.calibration_status}
          </span>
        </div>
        <ContributionList contributions={riskPayload.contributions ?? []} />
      </Section>

      <Section title="Affordability">
        <AffordabilityWorking payload={affordPayload} />
      </Section>

      <Section title="Coverage">
        <CoverageBreakdown payload={coveragePayload} />
      </Section>
    </div>
  );
}
