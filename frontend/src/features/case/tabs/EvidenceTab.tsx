import { useMemo, useState } from "react";

import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Chip } from "../../../components/ui/Chip";
import { EmptyState } from "../../../components/ui/EmptyState";
import { ErrorState } from "../../../components/ui/ErrorState";
import { PermissionDenied } from "../../../components/ui/PermissionDenied";
import { Select } from "../../../components/ui/Select";
import { formatDate, formatPaise } from "../../../lib/format";
import { CashflowTimeline, type CashflowPoint } from "../CashflowTimeline";
import { useEvidence, type CaseData, type EvidenceEvent } from "../useCase";

const CATEGORIES = [
  "SALARY",
  "GIG_INCOME",
  "BUSINESS_INCOME",
  "TRANSFER_IN",
  "RENT",
  "EMI",
  "UTILITY",
  "TELECOM",
  "MERCHANT",
  "CASH",
  "OTHER",
];

function monthKey(iso: string): string {
  return iso.slice(0, 7);
}

function aggregate(events: EvidenceEvent[]): CashflowPoint[] {
  const byMonth = new Map<string, { inflow: number; outflow: number }>();
  for (const event of events) {
    const key = monthKey(event.occurred_at);
    const bucket = byMonth.get(key) ?? { inflow: 0, outflow: 0 };
    const amount = event.amount_paise ?? 0;
    if (event.direction === "CREDIT") bucket.inflow += amount;
    else if (event.direction === "DEBIT") bucket.outflow += amount;
    byMonth.set(key, bucket);
  }
  return [...byMonth.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .slice(-6)
    .map(([month, totals]) => ({
      month,
      inflow_paise: totals.inflow,
      outflow_paise: totals.outflow,
    }));
}

function SourceList({ data }: { data: CaseData }) {
  if (data.sources.length === 0) {
    return (
      <EmptyState
        title="No evidence connected yet"
        description="This case is waiting on a connected source (bank, AA or a declared document) before it can be assessed."
      />
    );
  }
  return (
    <ul className="divide-y divide-border rounded border border-border">
      {data.sources.map((source) => (
        <li key={source.id} className="flex items-center justify-between gap-4 px-3 py-2 text-sm">
          <div className="flex items-center gap-2">
            <span className="font-medium text-ink">{source.source_type}</span>
            {source.tier ? <Badge tone="accent">{source.tier.replace(/_/g, " ")}</Badge> : null}
            <span className="text-muted">{source.status}</span>
          </div>
          <div className="flex items-center gap-4 text-xs text-muted">
            <span>
              {source.period_start ? formatDate(source.period_start) : "—"} →{" "}
              {source.period_end ? formatDate(source.period_end) : "—"}
            </span>
            <span>
              {source.freshness_days !== null ? `${source.freshness_days}d old` : "freshness —"}
            </span>
            <span>
              last sync {source.last_sync_at ? formatDate(source.last_sync_at) : "—"}
            </span>
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Evidence tab: the source list, the cash-flow shape, and a server-paginated, server-filtered
 * transaction table. The client never receives the whole ledger. */
export function EvidenceTab({ data, applicationId }: { data: CaseData; applicationId: string }) {
  const [category, setCategory] = useState("");

  // The chart reads the full (unfiltered) stream; the table follows the category filter.
  const chartQuery = useEvidence(applicationId, "");
  const tableQuery = useEvidence(applicationId, category);

  const chartRows = useMemo(
    () => chartQuery.data?.pages.flatMap((page) => page.rows) ?? [],
    [chartQuery.data],
  );
  const tableRows = useMemo(
    () => tableQuery.data?.pages.flatMap((page) => page.rows) ?? [],
    [tableQuery.data],
  );
  const cashflow = useMemo(() => aggregate(chartRows), [chartRows]);

  return (
    <div data-testid="case-tab-body" className="space-y-6 case-wide:grid case-wide:grid-cols-2 case-wide:gap-8 case-wide:space-y-0">
      <SourceList data={data} />

      <section aria-label="Cash flow" className="space-y-2">
        <h2 className="text-sm font-medium text-ink">Cash flow (6 months)</h2>
        {chartQuery.isError ? chartQuery.error.status === 403 ? <PermissionDenied reason={chartQuery.error.message} /> : <ErrorState title="Could not load cash flow" message={chartQuery.error.message} correlationId={chartQuery.error.correlationId} onRetry={() => { void chartQuery.refetch(); }} /> : <CashflowTimeline data={cashflow} />}
      </section>

      <section aria-label="Transactions" className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-ink">Transactions</h2>
          <label className="flex items-center gap-2 text-xs text-muted">
            Category
            <Select
              className="w-40"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
            >
              <option value="">All</option>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c.replace(/_/g, " ")}
                </option>
              ))}
            </Select>
          </label>
        </div>

        {tableQuery.isError ? tableQuery.error.status === 403 ? <PermissionDenied reason={tableQuery.error.message} /> : <ErrorState title="Could not load transactions" message={tableQuery.error.message} correlationId={tableQuery.error.correlationId} onRetry={() => { void tableQuery.refetch(); }} /> : <div className="overflow-auto rounded border border-border">
          <table className="w-full border-collapse text-sm">
            <caption className="sr-only">Classified transactions</caption>
            <thead className="bg-sunken">
              <tr>
                <th scope="col" className="h-row px-3 text-left font-medium text-muted">Date</th>
                <th scope="col" className="h-row px-3 text-left font-medium text-muted">Description</th>
                <th scope="col" className="h-row px-3 text-left font-medium text-muted">Category</th>
                <th scope="col" className="h-row px-3 text-right font-medium text-muted">Amount</th>
                <th scope="col" className="h-row px-3 text-right font-medium text-muted">Balance</th>
              </tr>
            </thead>
            <tbody>
              {tableRows.map((event) => (
                <tr key={event.id} className="border-t border-border">
                  <td className="h-row px-3 text-left text-ink">{formatDate(event.occurred_at)}</td>
                  <td className="h-row px-3 text-left text-ink">{event.description ?? "—"}</td>
                  <td className="h-row px-3 text-left">
                    <Chip tone="neutral">{event.category.replace(/_/g, " ")}</Chip>
                    <span className="ml-2 text-xs text-muted">
                      {event.classification_method ?? "UNCLASSIFIED"}
                    </span>
                  </td>
                  <td className="h-row px-3 text-right tabular-nums text-ink">
                    {event.amount_paise !== null ? formatPaise(event.amount_paise) : "—"}
                  </td>
                  <td className="h-row px-3 text-right tabular-nums text-muted">
                    {event.balance_paise !== null ? formatPaise(event.balance_paise) : "—"}
                  </td>
                </tr>
              ))}
              {tableRows.length === 0 && !tableQuery.isLoading ? (
                <tr>
                  <td colSpan={5} className="h-row px-3 text-center text-muted">
                    No transactions in this category.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>}

        {tableQuery.hasNextPage ? (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void tableQuery.fetchNextPage()}
            disabled={tableQuery.isFetchingNextPage}
          >
            {tableQuery.isFetchingNextPage ? "Loading…" : "Load more"}
          </Button>
        ) : null}
      </section>
    </div>
  );
}
