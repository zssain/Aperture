import type { ReactNode } from "react";

import { InfoHint } from "../../../components/ui/InfoHint";
import { MetricValue } from "../../../components/ui/MetricValue";
import { AffordabilityWorking } from "../AffordabilityWorking";
import { ContributionList } from "../ContributionList";
import { CoverageBreakdown } from "../CoverageBreakdown";
import type {
  AffordabilityPayload,
  BureauMetric,
  CaseData,
  CoveragePayload,
  RiskPayload,
} from "../useCase";

function BureauStat({ label, metric }: { label: string; metric: BureauMetric }) {
  return (
    <div className="rounded border border-border bg-surface p-3">
      <dt className="eyebrow text-muted">{label}</dt>
      <dd className="mt-1 text-heading font-semibold text-ink">
        <MetricValue value={metric.value} status={metric.status} precision={0} />
      </dd>
    </div>
  );
}

function Section({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section aria-label={title} className="space-y-3">
      <h2 className="flex items-center gap-1.5 eyebrow">
        {title}
        {hint}
      </h2>
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
      <Section title="Probability of default" hint={<InfoHint term="pd" />}>
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="text-title font-semibold">
            <MetricValue
              value={pd !== null ? pd * 100 : null}
              status={pdStatus}
              precision={1}
              unit="%"
            />
          </span>
          <span className="inline-flex items-center gap-1.5 font-mono text-xs text-muted">
            {risk.model_version ?? "model —"} · {risk.calibration_status}
            {pdStatus === "uncalibrated" ? <InfoHint term="uncalibrated" /> : null}
          </span>
        </div>
        <ContributionList contributions={riskPayload.contributions ?? []} />
      </Section>

      <Section title="Affordability" hint={<InfoHint term="dsr" />}>
        <AffordabilityWorking payload={affordPayload} />
      </Section>

      <Section title="Coverage" hint={<InfoHint term="evidence_coverage" />}>
        <CoverageBreakdown payload={coveragePayload} />
      </Section>

      <Section title="Credit bureau" hint={<InfoHint term="bureau" />}>
        {data.bureau.present ? (
          <dl className="grid grid-cols-3 gap-3">
            <BureauStat label="Score" metric={data.bureau.score} />
            <BureauStat label="Active loans" metric={data.bureau.active_loans} />
            <BureauStat label="Delinquencies · 12m" metric={data.bureau.delinquencies_12m} />
          </dl>
        ) : (
          <p className="text-sm text-muted">
            No credit-bureau file on this applicant — the decision rests on cash-flow
            evidence. Bureau signals show here as “—”, never as zero.
          </p>
        )}
      </Section>
    </div>
  );
}
