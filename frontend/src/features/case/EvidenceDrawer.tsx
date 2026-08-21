import { Badge } from "../../components/ui/Badge";
import { Drawer } from "../../components/ui/Drawer";
import { Skeleton } from "../../components/ui/Skeleton";
import { formatNumber } from "../../lib/format";
import { useLineage } from "./useCase";

function humanize(featureKey: string): string {
  return featureKey.replace(/_paise$/, " (paise)").replace(/_/g, " ");
}

/** The evidence drawer: the definition, formula, window, computed value and the exact events a
 * number was computed from. Opened by clicking any number; state lives in the URL. The Drawer
 * primitive traps focus and restores it to the trigger on close. */
export function EvidenceDrawer({
  snapshotId,
  featureKey,
  onClose,
}: {
  snapshotId: string | null;
  featureKey: string | null;
  onClose: () => void;
}) {
  const query = useLineage(snapshotId, featureKey);
  const open = Boolean(featureKey);
  const lineage = query.data;

  return (
    <Drawer
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      title={featureKey ? humanize(featureKey) : "Feature"}
      description="Definition, formula, and the events this number was computed from."
    >
      {query.isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-4 w-64" />
          <Skeleton className="h-4 w-40" />
        </div>
      ) : query.isError ? (
        <p className="text-sm text-negative">Could not load lineage: {query.error.message}</p>
      ) : lineage ? (
        <dl className="space-y-4 text-sm">
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">Value</dt>
            <dd className="tabular-nums text-ink">
              {lineage.value !== null
                ? formatNumber(lineage.value, lineage.dtype === "float" ? 3 : 0)
                : `— (${lineage.null_reason ?? "null"})`}
              {lineage.value !== null ? (
                <Badge tone={lineage.matches ? "positive" : "caution"} className="ml-2">
                  {lineage.matches ? "recomputed ✓" : "recompute differs"}
                </Badge>
              ) : null}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">Formula</dt>
            <dd className="text-ink">{lineage.formula_doc}</dd>
          </div>
          <div className="flex gap-6">
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted">Window</dt>
              <dd className="text-ink">{lineage.window}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted">Version</dt>
              <dd className="font-mono text-ink">{lineage.version}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted">Direction</dt>
              <dd className="text-ink">{lineage.monotonic_direction.replace(/_/g, " ")}</dd>
            </div>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">
              Contributing events ({lineage.contributing_event_ids.length})
            </dt>
            <dd>
              {lineage.contributing_event_ids.length === 0 ? (
                <span className="text-muted">None — computed from an empty set.</span>
              ) : (
                <ul className="mt-1 max-h-48 space-y-1 overflow-auto font-mono text-xs text-muted">
                  {lineage.contributing_event_ids.map((id) => (
                    <li key={id}>{id}</li>
                  ))}
                </ul>
              )}
            </dd>
          </div>
        </dl>
      ) : null}
    </Drawer>
  );
}
