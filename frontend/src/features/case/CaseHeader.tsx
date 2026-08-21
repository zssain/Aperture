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

interface FactProps {
  label: string;
  children: React.ReactNode;
}

function Fact({ label, children }: FactProps) {
  return (
    <div className="flex flex-col">
      <span className="eyebrow">{label}</span>
      <span className="text-sm font-medium tabular-nums text-ink">{children}</span>
    </div>
  );
}

/** The case header. A disabled action bar names WHY it is disabled (wrong role, already
 * resolved) — an honest disabled control, never a silent hide. */
export function CaseHeader({ data, actions }: { data: CaseData; actions: CaseActions }) {
  const { applicant, application } = data;
  const amount = application.requested_amount_paise;
  const tenor = application.requested_tenor_months;

  const tiers = Array.from(
    new Set(data.sources.map((source) => source.tier).filter((tier): tier is string => Boolean(tier))),
  );

  return (
    <header className="border-b border-border pb-4 pt-4 md:pt-0">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 space-y-1">
          <p className="eyebrow">Case file</p>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-title font-semibold text-ink">
              {applicant.display_name ?? applicant.external_ref}
            </h1>
            <span className="font-mono text-sm text-muted">{applicant.external_ref}</span>
          </div>
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
              icon="check"
              loading={actions.busy}
              disabled={actions.disabled}
              title={actions.disabled ? actions.disabledReason : undefined}
              onClick={actions.onConfirm}
            >
              {actions.busy ? "Recording…" : "Confirm recommendation"}
            </Button>
          </div>
          {actions.disabled && actions.disabledReason ? (
            <p className="max-w-xs text-right text-xs text-muted">{actions.disabledReason}</p>
          ) : null}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-start gap-x-8 gap-y-3">
        <Fact label="Requested">
          {amount !== null ? formatPaise(amount) : "Not set"}
        </Fact>
        {tenor !== null ? <Fact label="Tenor">{tenor} months</Fact> : null}
        <Fact label="Case age">{formatAge(data.case_age_seconds)}</Fact>
        {tiers.length > 0 ? (
          <div className="flex flex-col gap-1">
            <span className="eyebrow">Evidence tier</span>
            <div className="flex flex-wrap gap-1.5">
              {tiers.map((tier) => (
                <Badge key={tier} tone="accent">
                  {TIER_LABELS[tier] ?? tier}
                </Badge>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </header>
  );
}
