import { formatPaise } from "../../lib/format";
import { AssessmentChips } from "./AssessmentChips";
import type { CaseData, CaseDecision } from "./useCase";

const OUTCOME_PHRASE: Record<string, string> = {
  APPROVE_ENHANCED: "Approved at the enhanced band",
  APPROVE_STANDARD: "Approved at the standard band",
  APPROVE_STARTER: "Approved at the starter band",
  DECLINE_RISK: "Declined on risk",
  DECLINE_AFFORDABILITY: "Declined on affordability",
  REVIEW_EVIDENCE: "Routed for more evidence",
  REVIEW_FRAUD: "Routed for verification review",
  FRAUD_REVIEW: "Routed for fraud review",
  SYSTEM_UNAVAILABLE: "System unavailable",
};

function termsLine(decision: CaseDecision): string {
  const terms = decision.terms;
  const principal = terms.approved_principal_paise;
  if (typeof principal !== "number" || principal <= 0) {
    return decision.outcome.replace(/_/g, " ");
  }
  const tenor = terms.approved_tenor_months;
  const rateBps = terms.annual_rate_bps;
  const parts = [formatPaise(principal)];
  if (typeof tenor === "number") parts.push(`${tenor} months`);
  if (typeof rateBps === "number") parts.push(`${(rateBps / 100).toFixed(0)}% APR`);
  const graduation = terms.graduation as { review_months?: number } | null | undefined;
  if (graduation && typeof graduation.review_months === "number") {
    parts.push(`step-up review month ${graduation.review_months}`);
  }
  return `${decision.outcome} — ${parts.join(" · ")}`;
}

function routedBecause(decision: CaseDecision): string {
  const gate = decision.fired_rules.find((rule) => {
    const number = Number(rule.number);
    return number >= 1 && number <= 9;
  });
  const phrase = OUTCOME_PHRASE[decision.outcome] ?? decision.outcome.replace(/_/g, " ");
  const name = gate ? String(gate.name).replace(/_/g, " ") : "policy";
  return `${phrase} (${name})`;
}

/** The decision band — full width, deliberately NOT inside a card. When an assessment was
 * unavailable there is no decision, so the band says so: three-of-four is not a decision. */
export function DecisionBand({
  data,
  onSelectTab,
}: {
  data: CaseData;
  onSelectTab: (tab: string) => void;
}) {
  const noDecision = data.assessment_failed || data.decision === null;

  return (
    <section aria-label="Decision" className="space-y-3 border-b border-border py-4">
      {noDecision ? (
        <p className="text-[24px] font-semibold leading-tight text-negative">
          NO DECISION — SYSTEM UNAVAILABLE
        </p>
      ) : (
        <>
          <p className="text-[24px] font-semibold leading-tight text-ink">
            {termsLine(data.decision as CaseDecision)}
          </p>
          <p className="text-[15px] text-muted">
            Routed because: {routedBecause(data.decision as CaseDecision)}
          </p>
        </>
      )}
      <AssessmentChips chips={data.chips} onSelectTab={onSelectTab} />
    </section>
  );
}
