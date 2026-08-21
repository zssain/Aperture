import { LedgerTimeline } from "../LedgerTimeline";
import { ReplayPanel } from "../ReplayPanel";
import type { CaseData } from "../useCase";

function ruleLine(rule: Record<string, unknown>): string {
  const number = rule.number ?? "?";
  const name = String(rule.name ?? "").replace(/_/g, " ");
  const outcome = String(rule.outcome ?? "");
  return `Rule ${number}: ${name} → ${outcome}`;
}

/** Decision & Audit tab: the ordered rules that fired, the chained ledger timeline, replay, and
 * the bureau-only counterfactual. */
export function DecisionAuditTab({ data }: { data: CaseData }) {
  const decision = data.decision;
  if (!decision) {
    return <p className="text-sm text-negative">No decision was recorded for this case.</p>;
  }

  return (
    <div data-testid="case-tab-body" className="space-y-8 case-wide:grid case-wide:grid-cols-2 case-wide:gap-8 case-wide:space-y-0">
      <section aria-label="Policy rules" className="space-y-2">
        <h3 className="text-sm font-medium text-ink">Recommendation</h3>
        <p className="text-sm text-muted">
          {decision.outcome.replace(/_/g, " ")} · policy v{decision.policy_version ?? "—"}
        </p>
        <ol className="space-y-1">
          {decision.fired_rules.map((rule, index) => (
            <li key={index} className="font-mono text-sm text-ink">
              {ruleLine(rule)}
            </li>
          ))}
        </ol>
      </section>

      <section aria-label="Audit trail" className="space-y-2">
        <h3 className="text-sm font-medium text-ink">Audit trail</h3>
        <LedgerTimeline decisionId={decision.id} />
      </section>

      <ReplayPanel decisionId={decision.id} />

      <section aria-label="Bureau-only counterfactual" className="space-y-1">
        <h3 className="text-sm font-medium text-ink">Bureau-only counterfactual</h3>
        <p className="text-sm text-ink">{data.bureau_only.outcome.replace(/_/g, " ")}</p>
        <p className="text-sm text-muted">{data.bureau_only.note}</p>
      </section>
    </div>
  );
}
