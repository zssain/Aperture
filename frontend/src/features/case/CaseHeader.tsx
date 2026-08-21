import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { formatPaise } from "../../lib/format";
import type { CaseData } from "./useCase";

function formatAge(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  if (hours < 1) return "< 1h old";
  if (hours < 24) return `${hours}h old`;
  const days = Math.floor(hours / 24);
  return `${days}d old`;
}

const TIER_LABELS: Record<string, string> = {
  AA_VERIFIED: "AA verified",
  BANK_VERIFIED: "Bank verified",
  DECLARED_DOCUMENT: "Declared",
};

export interface CaseActions {
  onConfirm: () => void;
  onOverride: () => void;
  onRequestEvidence: () => void;
  disabled: boolean;
  disabledReason: string;
  busy: boolean;
}

/** Fixed case header. A disabled action bar names WHY it is disabled (wrong role, already
 * resolved) — an honest disabled control, never a silent hide. */
export function CaseHeader({ data, actions }: { data: CaseData; actions: CaseActions }) {
  const { applicant, application } = data;
  const amount = application.requested_amount_paise;
  const tenor = application.requested_tenor_months;

  const tiers = Array.from(
    new Set(data.sources.map((source) => source.tier).filter((tier): tier is string => Boolean(tier))),
  );

  return (
    <header className="flex items-start justify-between gap-4 border-b border-border pb-4">
      <div className="space-y-1">
        <div className="flex items-center gap-3">
          <h1 className="text-heading font-semibold text-ink">
            {applicant.display_name ?? applicant.external_ref}
          </h1>
          <span className="font-mono text-xs text-muted">{applicant.external_ref}</span>
        </div>
        <p className="text-sm text-muted">
          {amount !== null ? formatPaise(amount) : "Amount not set"}
          {tenor !== null ? ` · ${tenor} months` : ""}
          {` · ${formatAge(data.case_age_seconds)}`}
        </p>
        {tiers.length > 0 ? (
          <div className="flex flex-wrap gap-2 pt-1">
            {tiers.map((tier) => (
              <Badge key={tier} tone="accent">
                {TIER_LABELS[tier] ?? tier}
              </Badge>
            ))}
          </div>
        ) : null}
      </div>

      <div className="flex shrink-0 flex-col items-end gap-1">
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            disabled={actions.disabled || actions.busy}
            title={actions.disabled ? actions.disabledReason : undefined}
            onClick={actions.onRequestEvidence}
          >
            Request evidence
          </Button>
          <Button
            variant="secondary"
            size="sm"
            disabled={actions.disabled || actions.busy}
            title={actions.disabled ? actions.disabledReason : undefined}
            onClick={actions.onOverride}
          >
            Override
          </Button>
          <Button
            variant="primary"
            size="sm"
            disabled={actions.disabled || actions.busy}
            title={actions.disabled ? actions.disabledReason : undefined}
            onClick={actions.onConfirm}
          >
            {actions.busy ? "Recording…" : "Confirm recommendation"}
          </Button>
        </div>
        {actions.disabled && actions.disabledReason ? (
          <p className="text-xs text-muted">{actions.disabledReason}</p>
        ) : null}
      </div>
    </header>
  );
}
