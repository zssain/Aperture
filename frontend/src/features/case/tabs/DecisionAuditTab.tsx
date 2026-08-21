import { Chip } from "../../../components/ui/Chip";
import { InfoHint } from "../../../components/ui/InfoHint";
import { LedgerTimeline } from "../LedgerTimeline";
import { ReplayPanel } from "../ReplayPanel";
import type { CaseData } from "../useCase";

function ruleLine(rule: Record<string, unknown>): { number: string; name: string; outcome: string } {
  return {
    number: String(rule.number ?? "?"),
    name: String(rule.name ?? "").replace(/_/g, " "),
    outcome: String(rule.outcome ?? ""),
  };
}

/** Decision & Audit tab: the recommendation and the ordered rules that fired, the
 * chained ledger timeline, deterministic replay, and the bureau-only counterfactual.
 * Presented as a trustworthy audit workspace. */
export function DecisionAuditTab({ data }: { data: CaseData }) {
  const decision = data.decision;
  if (!decision) {
    return <p className="text-sm text-negative">No decision was recorded for this case.</p>;
  }

  return (
    <div data-testid="case-tab-body" className="space-y-8 case-wide:grid case-wide:grid-cols-2 case-wide:gap-8 case-wide:space-y-0">
      <section aria-label="Policy rules" className="space-y-3">
        <div className="flex items-center gap-2">
          <h3 className="eyebrow">Recommendation</h3>
          <InfoHint term="policy_version" />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-body font-medium text-ink">
            {decision.outcome.replace(/_/g, " ")}
          </span>
          <Chip tone="neutral" className="font-mono">
            policy v{decision.policy_version ?? "—"}
          </Chip>
        </div>
        <ol className="divide-y divide-border rounded border border-border">
          {decision.fired_rules.map((rule, index) => {
            const line = ruleLine(rule);
            return (
              <li key={index} className="flex items-center gap-3 px-3 py-2 text-sm">
                <span className="font-mono text-xs text-muted">R{line.number}</span>
                <span className="flex-1 text-ink">{line.name}</span>
                <Chip tone="neutral" className="font-mono">{line.outcome}</Chip>
              </li>
            );
          })}
        </ol>
      </section>

      <section aria-label="Audit trail" className="space-y-3">
        <h3 className="eyebrow">Audit trail</h3>
        <LedgerTimeline decisionId={decision.id} />
      </section>

      <ReplayPanel decisionId={decision.id} />

      <section aria-label="Bureau-only counterfactual" className="space-y-2">
        <div className="flex items-center gap-2">
          <h3 className="eyebrow">Bureau-only counterfactual</h3>
          <InfoHint term="bureau_only_counterfactual" />
        </div>
        <p className="text-body font-medium text-ink">
          {data.bureau_only.outcome.replace(/_/g, " ")}
        </p>
        <p className="text-sm text-muted">{data.bureau_only.note}</p>
      </section>
    </div>
  );
}
