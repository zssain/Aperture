import type { ReactNode } from "react";

import { Chip } from "../../components/ui/Chip";
import { Icon } from "../../components/ui/Icon";
import { formatPaise } from "../../lib/format";
import type { CaseData, CaseDecision } from "./useCase";

/** A short, readable headline per outcome. The exact enum stays visible in the mono
 * chip beside it — an auditor needs the precise token. */
const OUTCOME_HEADLINE: Record<string, string> = {
  APPROVE_ENHANCED: "Approve · enhanced band",
  APPROVE_STANDARD: "Approve · standard band",
  APPROVE_STARTER: "Approve · starter band",
  DECLINE_RISK: "Decline · risk",
  DECLINE_AFFORDABILITY: "Decline · affordability",
  REVIEW_EVIDENCE: "Refer · more evidence needed",
  REVIEW_FRAUD: "Refer · verification review",
  FRAUD_REVIEW: "Refer · fraud review",
  SYSTEM_UNAVAILABLE: "System unavailable",
};

const OUTCOME_RULE_PHRASE: Record<string, string> = {
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

function headline(outcome: string): string {
  return OUTCOME_HEADLINE[outcome] ?? outcome.replace(/_/g, " ");
}

function routedBecause(decision: CaseDecision): string {
  const gate = decision.fired_rules.find((rule) => {
    const number = Number(rule.number);
    return number >= 1 && number <= 9;
  });
  const phrase = OUTCOME_RULE_PHRASE[decision.outcome] ?? decision.outcome.replace(/_/g, " ");
  const name = gate ? String(gate.name).replace(/_/g, " ") : "policy";
  return `${phrase} (${name})`;
}

interface Fact {
  label: string;
  value: string;
}

/** The approved terms as discrete labelled facts, not one run-on string. */
function approvedTerms(decision: CaseDecision): Fact[] {
  const terms = decision.terms;
  const principal = terms.approved_principal_paise;
  if (typeof principal !== "number" || principal <= 0) return [];
  const facts: Fact[] = [{ label: "Principal", value: formatPaise(principal) }];
  if (typeof terms.approved_tenor_months === "number") {
    facts.push({ label: "Tenor", value: `${terms.approved_tenor_months} months` });
  }
  if (typeof terms.annual_rate_bps === "number") {
    facts.push({ label: "Rate", value: `${(terms.annual_rate_bps / 100).toFixed(0)}% APR` });
  }
  const graduation = terms.graduation as { review_months?: number } | null | undefined;
  if (graduation && typeof graduation.review_months === "number") {
    facts.push({ label: "Step-up review", value: `Month ${graduation.review_months}` });
  }
  return facts;
}

function FactItem({ label, value }: Fact) {
  return (
    <div className="flex flex-col">
      <span className="eyebrow">{label}</span>
      <span className="text-body font-medium tabular-nums text-ink">{value}</span>
    </div>
  );
}

/**
 * The decision summary — full width, deliberately NOT inside a card. When an
 * assessment was unavailable there is no decision, so it says so: three-of-four is
 * not a decision.
 */
export function DecisionSummary({ data }: { data: CaseData }): ReactNode {
  const noDecision = data.assessment_failed || data.decision === null;

  if (noDecision) {
    return (
      <section aria-label="Decision" className="border-b border-border py-4">
        <div className="flex items-center gap-2 text-negative">
          <Icon name="alert" size={22} />
          <p className="text-title font-semibold leading-tight">
            NO DECISION — SYSTEM UNAVAILABLE
          </p>
        </div>
        <p className="mt-2 text-sm text-muted">
          An assessment could not be produced, so the policy engine did not return a
          decision. A partial reading is not a decision.
        </p>
      </section>
    );
  }

  const decision = data.decision as CaseDecision;
  const facts = approvedTerms(decision);

  return (
    <section aria-label="Decision" className="space-y-3 border-b border-border py-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h2 className="text-title font-semibold leading-tight text-ink">
          {headline(decision.outcome)}
        </h2>
        {/* The precise enum token, kept for the audit reader. */}
        <Chip tone="neutral" className="font-mono">
          {decision.outcome}
        </Chip>
      </div>
      <p className="text-sm text-muted">Routed because: {routedBecause(decision)}</p>
      {facts.length > 0 ? (
        <div className="flex flex-wrap gap-x-8 gap-y-2 pt-1">
          {facts.map((fact) => (
            <FactItem key={fact.label} {...fact} />
          ))}
        </div>
      ) : null}
    </section>
  );
}
