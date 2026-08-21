import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { cn } from "../../lib/cn";
import { formatDate, formatPaise } from "../../lib/format";
import type { RecourseOption as RecourseOptionData } from "./useCase";

const LEVER_LABELS: Record<string, string> = {
  ADD_SOURCE: "Connect an additional source",
  EXTEND_HISTORY: "Provide a longer history",
  REDUCE_AMOUNT: "Apply for a smaller amount",
  ACCEPT_STARTER: "Accept a starter facility",
};

function deltaText(delta: Record<string, unknown>): string | null {
  const entries = Object.entries(delta).filter(([, v]) => typeof v === "number");
  if (entries.length === 0) return null;
  return entries
    .map(([key, value]) => `${key.replace(/_/g, " ")} ${Number(value) >= 0 ? "+" : ""}${value}`)
    .join(" · ");
}

/** A recourse option — a legitimately independent, actionable card: the action, who takes it,
 * the projected decision, the delta, the policy version, and the expiry. An expired option is
 * greyed with a re-run affordance rather than silently dropped. */
export function RecourseOption({
  option,
  policyVersion,
  now,
  onRerun,
}: {
  option: RecourseOptionData;
  policyVersion: string | null;
  now: Date;
  onRerun: () => void;
}) {
  const change = option.required_change;
  const lever = String(change.lever ?? "ADD_SOURCE");
  const expiresRaw = change.expires_at ? String(change.expires_at) : null;
  const expired = expiresRaw ? new Date(expiresRaw) < now : false;
  const delta = deltaText((change.projected_delta as Record<string, unknown>) ?? {});

  return (
    <article
      className={cn(
        "flex flex-col gap-2 rounded border p-4",
        expired ? "border-border opacity-60" : "border-border bg-surface",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-medium text-ink">{LEVER_LABELS[lever] ?? lever}</h3>
        {option.projected_action ? (
          <Badge tone="positive" glyph>
            {option.projected_action}
          </Badge>
        ) : null}
      </div>
      <p className="text-xs text-muted">Taken by the applicant</p>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        {option.projected_limit_paise !== null ? (
          <>
            <dt className="text-muted">Projected limit</dt>
            <dd className="tabular-nums text-ink">{formatPaise(option.projected_limit_paise)}</dd>
          </>
        ) : null}
        {delta ? (
          <>
            <dt className="text-muted">Delta</dt>
            <dd className="text-ink">{delta}</dd>
          </>
        ) : null}
        <dt className="text-muted">Policy version</dt>
        <dd className="font-mono text-ink">{policyVersion ?? "—"}</dd>
        <dt className="text-muted">Expires</dt>
        <dd className={cn("text-ink", expired ? "text-negative" : "")}>
          {expiresRaw ? formatDate(expiresRaw) : "—"}
          {expired ? " (expired)" : ""}
        </dd>
      </dl>
      {expired ? (
        <Button variant="secondary" size="sm" onClick={onRerun}>
          Re-run recourse
        </Button>
      ) : null}
    </article>
  );
}
