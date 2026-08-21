import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { useReplay } from "./useReview";

/** Replay re-runs the decision over its stored snapshot. IDENTICAL is the expected result and is
 * shown in positive colour; DIVERGED is a serious signal — shown prominently in negative colour
 * with the field-level diff and a correlation ID for escalation, never as a passing state. */
export function ReplayPanel({ decisionId }: { decisionId: string }) {
  const replay = useReplay(decisionId);
  const result = replay.data;
  const diverged = result?.status === "DIVERGED";

  return (
    <section aria-label="Replay" className="space-y-3">
      <div className="flex items-center gap-3">
        <Button
          variant="secondary"
          size="sm"
          onClick={() => replay.mutate()}
          disabled={replay.isPending}
        >
          {replay.isPending ? "Replaying…" : "Replay decision"}
        </Button>
        {result ? (
          <Badge tone={diverged ? "negative" : "positive"}>{result.status}</Badge>
        ) : null}
      </div>

      {replay.isError ? (
        <p role="alert" className="text-sm text-negative">
          Replay failed: {replay.error.message}
          <span className="ml-2 font-mono text-xs">{replay.error.correlationId}</span>
        </p>
      ) : null}

      {diverged && result ? (
        <div role="alert" className="space-y-2 rounded border border-negative bg-surface p-3">
          <p className="font-medium text-negative">
            Replay diverged from the stored decision. Escalate this — it must not be treated as a
            pass.
          </p>
          <table className="w-full border-collapse text-sm">
            <caption className="sr-only">Field-level replay diff</caption>
            <thead>
              <tr className="text-muted">
                <th scope="col" className="py-1 text-left font-medium">Field</th>
                <th scope="col" className="py-1 text-left font-medium">Stored</th>
                <th scope="col" className="py-1 text-left font-medium">Recomputed</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(result.diff).map(([field, values]) => (
                <tr key={field} className="border-t border-border">
                  <th scope="row" className="py-1 text-left font-normal text-ink">{field}</th>
                  <td className="py-1 text-left tabular-nums text-ink">{JSON.stringify(values.stored)}</td>
                  <td className="py-1 text-left tabular-nums text-negative">
                    {JSON.stringify(values.recomputed)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {result && !diverged ? (
        <p className="text-sm text-positive">
          The decision reproduced exactly over its stored snapshot.
        </p>
      ) : null}
    </section>
  );
}
