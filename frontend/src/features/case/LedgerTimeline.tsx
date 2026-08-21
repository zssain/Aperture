import { Skeleton } from "../../components/ui/Skeleton";
import { formatDateTime } from "../../lib/format";
import { useDecisionLedger } from "./useReview";

function truncate(hash: string): string {
  return hash.length > 12 ? `${hash.slice(0, 12)}…` : hash;
}

const EVENT_LABELS: Record<string, string> = {
  DECISION_MADE: "Decision made",
  DECISION_REVIEWED: "Reviewed by human",
  RECOURSE_SENT: "Recourse sent",
};

/** The chained audit trail for this decision: actor, action, timestamp and the truncated payload
 * hash in mono. The chain (prev_hash → payload_hash) is what makes the record tamper-evident. */
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
    <ol className="space-y-2">
      {entries.map((entry) => (
        <li key={entry.seq} className="flex items-start gap-3 border-l-2 border-border pl-3">
          <div className="min-w-0 flex-1">
            <p className="text-sm text-ink">
              <span className="font-medium">{EVENT_LABELS[entry.event_type] ?? entry.event_type}</span>
              {entry.actor_email ? <span className="text-muted"> · {entry.actor_email}</span> : null}
            </p>
            <p className="text-xs text-muted">{formatDateTime(entry.created_at)}</p>
            <p className="font-mono text-xs text-muted">
              #{entry.seq} · {truncate(entry.prev_hash)} → {truncate(entry.payload_hash)}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}
