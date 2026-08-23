import { useMemo, useState } from "react";

import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { EmptyState } from "../../../components/ui/EmptyState";
import { ErrorState } from "../../../components/ui/ErrorState";
import { PermissionDenied } from "../../../components/ui/PermissionDenied";
import { Select } from "../../../components/ui/Select";
import { Skeleton } from "../../../components/ui/Skeleton";
import { cn } from "../../../lib/cn";
import { formatDate, formatPaise } from "../../../lib/format";
import { CashflowTimeline, type CashflowPoint } from "../CashflowTimeline";
import { sourceTypeLabel } from "../labels";
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

const TIER_LABELS: Record<string, string> = {
  AA_VERIFIED: "AA verified",
  BANK_VERIFIED: "Bank verified",
  DECLARED_DOCUMENT: "Declared",
};

function monthKey(iso: string): string {
  return iso.slice(0, 7);
}

export function aggregate(events: EvidenceEvent[]): CashflowPoint[] {
  const byMonth = new Map<string, { inflow: number; outflow: number }>();
  for (const event of events) {
    // A null amount is missing data, not ₹0 of flow. Skip it from the aggregate the
    // same way the transaction table renders it as "—"; never invent a zero.
    if (event.amount_paise === null || event.amount_paise === undefined) continue;
    const key = monthKey(event.occurred_at);
    const bucket = byMonth.get(key) ?? { inflow: 0, outflow: 0 };
    const amount = event.amount_paise;
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

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <span className="flex flex-col">
      <span className="eyebrow">{label}</span>
      <span className="text-xs tabular-nums text-ink">{value}</span>
    </span>
  );
}

function SourceList({ data }: { data: CaseData }) {
  if (data.sources.length === 0) {
    return (
      <EmptyState
        icon="bank"
        title="No evidence connected yet"
        description="This case is waiting on a connected source (bank, AA or a declared document) before it can be assessed."
      />
    );
  }
  return (
    <ul className="space-y-2">
      {data.sources.map((source) => (
        <li key={source.id} className="rounded border border-border bg-surface p-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-ink">{sourceTypeLabel(source.source_type)}</span>
            {source.tier ? (
              <Badge tone="accent">{TIER_LABELS[source.tier] ?? source.tier.replace(/_/g, " ")}</Badge>
            ) : null}
            <Badge tone={source.status === "CONNECTED" ? "positive" : "neutral"}>
              {source.status}
            </Badge>
          </div>
          <div className="mt-2 flex flex-wrap gap-x-6 gap-y-2">
            <Fact
              label="Period"
              value={`${source.period_start ? formatDate(source.period_start) : "—"} → ${
                source.period_end ? formatDate(source.period_end) : "—"
              }`}
            />
            <Fact
              label="Freshness"
              value={source.freshness_days !== null ? `${source.freshness_days}d old` : "—"}
            />
            <Fact
              label="Last sync"
              value={source.last_sync_at ? formatDate(source.last_sync_at) : "—"}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

/** One transaction amount, signed by direction where the field supports it. */
function TxnAmount({ event }: { event: EvidenceEvent }) {
  if (event.amount_paise === null) return <span className="text-muted">—</span>;
  const credit = event.direction === "CREDIT";
  const debit = event.direction === "DEBIT";
  return (
    <span className={cn("tabular-nums", credit ? "text-positive" : "text-ink")}>
      {credit ? "+" : debit ? "−" : ""}
      {formatPaise(event.amount_paise)}
    </span>
  );
}

/** Evidence tab: the source list, the cash-flow shape, and a server-paginated,
 * server-filtered transaction table. The client never receives the whole ledger. */
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
  const tableEmpty = tableRows.length === 0 && !tableQuery.isLoading;

  return (
    <div data-testid="case-tab-body" className="space-y-6 case-wide:grid case-wide:grid-cols-2 case-wide:gap-8 case-wide:space-y-0">
      <section aria-label="Connected sources" className="space-y-2">
        <h2 className="eyebrow">Connected sources</h2>
        <SourceList data={data} />
      </section>

      <section aria-label="Cash flow" className="space-y-2">
        <h2 className="eyebrow">Cash flow · last 6 months</h2>
        {chartQuery.isError ? (
          chartQuery.error.status === 403 ? (
            <PermissionDenied reason={chartQuery.error.message} />
          ) : (
            <ErrorState
              title="Could not load cash flow"
              message={chartQuery.error.message}
              correlationId={chartQuery.error.correlationId}
              onRetry={() => {
                void chartQuery.refetch();
              }}
            />
          )
        ) : (
          <CashflowTimeline data={cashflow} />
        )}
      </section>

      <section aria-label="Transactions" className="space-y-2 case-wide:col-span-2">
        <div className="flex items-center justify-between">
          <h2 className="eyebrow">Transactions</h2>
          <label className="flex items-center gap-2 text-xs text-muted">
            Category
            <Select
              className="h-9 w-40"
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

        {tableQuery.isError ? (
          tableQuery.error.status === 403 ? (
            <PermissionDenied reason={tableQuery.error.message} />
          ) : (
            <ErrorState
              title="Could not load transactions"
              message={tableQuery.error.message}
              correlationId={tableQuery.error.correlationId}
              onRetry={() => {
                void tableQuery.refetch();
              }}
            />
          )
        ) : tableEmpty ? (
          <EmptyState
            icon="document"
            title={category ? "No transactions in this category" : "No transactions yet"}
            description={
              category
                ? "Clear the category filter to see the full ledger."
                : "Transactions will appear here once a source with history is connected."
            }
            action={
              category ? (
                <Button variant="secondary" size="sm" onClick={() => setCategory("")}>
                  Clear filter
                </Button>
              ) : undefined
            }
          />
        ) : (
          <div className="overflow-auto rounded border border-border scrollbar-slim">
            <table className="w-full border-collapse text-sm">
              <caption className="sr-only">Classified transactions</caption>
              <thead className="bg-sunken">
                <tr>
                  <th scope="col" className="h-9 px-3 text-left text-eyebrow font-semibold text-muted">Date</th>
                  <th scope="col" className="h-9 px-3 text-left text-eyebrow font-semibold text-muted">Description</th>
                  <th scope="col" className="h-9 px-3 text-left text-eyebrow font-semibold text-muted">Category</th>
                  <th scope="col" className="h-9 px-3 text-right text-eyebrow font-semibold text-muted">Amount</th>
                  <th scope="col" className="h-9 px-3 text-right text-eyebrow font-semibold text-muted">Balance</th>
                </tr>
              </thead>
              <tbody>
                {tableQuery.isLoading
                  ? Array.from({ length: 6 }).map((_, index) => (
                      <tr key={index} className="border-t border-border">
                        {Array.from({ length: 5 }).map((__, cell) => (
                          <td key={cell} className="h-row px-3">
                            <Skeleton className="h-4 w-20" />
                          </td>
                        ))}
                      </tr>
                    ))
                  : tableRows.map((event) => (
                      <tr key={event.id} className="border-t border-border hover:bg-surface-subtle">
                        <td className="h-row px-3 text-left tabular-nums text-ink">{formatDate(event.occurred_at)}</td>
                        <td className="h-row px-3 text-left text-ink">{event.description ?? "—"}</td>
                        <td className="h-row px-3 text-left">
                          <Badge tone="neutral">{event.category.replace(/_/g, " ")}</Badge>
                          <span className="ml-2 text-xs text-muted">
                            {event.classification_method ?? "UNCLASSIFIED"}
                          </span>
                        </td>
                        <td className="h-row px-3 text-right">
                          <TxnAmount event={event} />
                        </td>
                        <td className="h-row px-3 text-right tabular-nums text-muted">
                          {event.balance_paise !== null ? formatPaise(event.balance_paise) : "—"}
                        </td>
                      </tr>
                    ))}
              </tbody>
            </table>
          </div>
        )}

        {tableQuery.hasNextPage ? (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void tableQuery.fetchNextPage()}
            disabled={tableQuery.isFetchingNextPage}
            loading={tableQuery.isFetchingNextPage}
          >
            Load more
          </Button>
        ) : null}
      </section>
    </div>
  );
}
