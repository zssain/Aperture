import { Skeleton } from "../../components/ui/Skeleton";
import { formatDateTime } from "../../lib/format";
import { useDecisionLedger } from "./useReview";

const EVENT_LABELS: Record<string, string> = {
  DECISION_MADE: "Decision made",
  DECISION_REVIEWED: "Reviewed by human",
  RECOURSE_SENT: "Recourse sent",
};

/** The chained audit trail for this decision as a vertical timeline: actor, action and
 * timestamp in the primary flow; the tamper-evident hash chain (prev_hash →
 * payload_hash) tucked into a secondary expandable so it never crowds the reading
 * flow — but is never removed. */
export function LedgerTimeline({ decisionId }: { decisionId: string }) {
  const query = useDecisionLedger(decisionId);

  if (query.isLoading) return <Skeleton className="h-24 w-full" />;
  if (query.isError) {
    return <p className="text-sm text-negative">Could not load the audit trail.</p>;
  }
  const entries = query.data ?? [];
  if (entries.length === 0) {
    return <p className="text-sm text-muted">No audit entries yet.</p>;
  }

  return (
    <ol className="space-y-0">
      {entries.map((entry, index) => (
        <li key={entry.seq} className="relative flex gap-3 pb-4 last:pb-0">
          {/* Rail + node. */}
          <div className="relative flex flex-col items-center">
            <span
              aria-hidden="true"
              className="mt-1 h-2.5 w-2.5 shrink-0 rounded-pill border-2 border-accent bg-surface"
            />
            {index < entries.length - 1 ? (
              <span aria-hidden="true" className="w-px flex-1 bg-border" />
            ) : null}
          </div>
          <div className="min-w-0 flex-1 pb-1">
            <p className="text-sm text-ink">
              <span className="font-medium">
                {EVENT_LABELS[entry.event_type] ?? entry.event_type}
              </span>
              {entry.actor_email ? (
                <span className="text-muted"> · {entry.actor_email}</span>
              ) : null}
            </p>
            <p className="text-xs text-muted">{formatDateTime(entry.created_at)}</p>
            <details className="mt-1 group">
              <summary className="cursor-pointer list-none text-xs text-muted underline decoration-dotted underline-offset-2 hover:text-ink">
                Hash chain
              </summary>
              <p className="mt-1 break-all font-mono text-xs text-muted">
                #{entry.seq} · {entry.prev_hash} → {entry.payload_hash}
              </p>
            </details>
          </div>
        </li>
      ))}
    </ol>
  );
}
