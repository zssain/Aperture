import type { KeyboardEvent, MouseEvent } from "react";
import { useRef } from "react";

import { Badge } from "../../components/ui/Badge";
import { Icon } from "../../components/ui/Icon";
import { MetricValue } from "../../components/ui/MetricValue";
import { Skeleton } from "../../components/ui/Skeleton";
import { StatusDot } from "../../components/ui/StatusDot";
import type { Tone } from "../../components/ui/tones";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { cn } from "../../lib/cn";
import { formatPaise } from "../../lib/format";
import type { QueueRow } from "./useQueue";
import { ChangeBadge } from "./ChangeBadge";

export interface QueueTableProps {
  rows: QueueRow[];
  loading: boolean;
  sort: string;
  onSort: (base: string) => void;
  onOpen: (row: QueueRow, newTab: boolean) => void;
}

interface ColumnSpec {
  key: string;
  header: string;
  numeric: boolean;
  sortBase?: string;
  width: string;
  responsive?: string;
}

const COLUMNS: ColumnSpec[] = [
  { key: "applicant", header: "Applicant", numeric: false, width: "17%" },
  { key: "amount", header: "Amount", numeric: true, sortBase: "amount", width: "10%", responsive: "hidden xl:table-cell" },
  { key: "sources", header: "Sources", numeric: false, width: "8%", responsive: "hidden xl:table-cell" },
  { key: "routed_because", header: "Routed because", numeric: false, width: "20%" },
  { key: "recommendation", header: "Recommendation", numeric: false, width: "16%" },
  { key: "pd", header: "PD", numeric: true, sortBase: "pd", width: "7%" },
  { key: "coverage", header: "Coverage", numeric: true, sortBase: "coverage", width: "8%" },
  { key: "verification", header: "Verification", numeric: false, width: "8%" },
  { key: "waiting", header: "Waiting", numeric: true, sortBase: "waiting", width: "7%" },
];

const ACTION_LABELS: Record<string, string> = {
  APPROVE: "Approve",
  APPROVE_STARTER: "Approve · starter",
  DECLINE: "Decline",
  REFER: "Refer",
};

/** Tone for the one badged column — the recommendation. */
const ACTION_TONE: Record<string, Tone> = {
  APPROVE: "positive",
  APPROVE_STARTER: "positive",
  DECLINE: "negative",
  REFER: "caution",
};

const VERIFICATION_TONE: Record<string, Tone> = {
  CLEAR: "positive",
  ELEVATED: "caution",
  HIGH: "negative",
  UNKNOWN: "neutral",
};

function formatWaiting(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  if (hours < 1) return "< 1h";
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  return `${days}d ${hours % 24}h`;
}

function sortDirection(
  column: ColumnSpec,
  sort: string,
): "ascending" | "descending" | "none" | undefined {
  if (!column.sortBase) return undefined;
  const base = sort.replace(/^-/, "");
  if (base !== column.sortBase) return "none";
  return sort.startsWith("-") ? "descending" : "ascending";
}

/** An arrow that reflects the current sort direction (and hints on inactive cols). */
function SortArrow({ direction }: { direction: "ascending" | "descending" | "none" }) {
  if (direction === "none") {
    return <Icon name="chevron-down" size={13} className="opacity-30" />;
  }
  return (
    <Icon name={direction === "ascending" ? "chevron-up" : "chevron-down"} size={13} />
  );
}

function ApplicantCell({ row }: { row: QueueRow }) {
  return (
    <div className="flex flex-col">
      <span className="flex items-center gap-2">
        <span className={cn("font-medium", row.superseded ? "text-muted" : "text-ink")}>
          {row.applicant_name}
        </span>
        {row.superseded ? (
          <span
            title="A later decision replaced this one; opening the case shows the current decision."
            className="rounded bg-sunken px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted"
          >
            Superseded
          </span>
        ) : null}
      </span>
      <span className="text-xs text-muted">{row.applicant_ref}</span>
    </div>
  );
}

function RecommendationCell({ row }: { row: QueueRow }) {
  const rec = row.recommendation;
  return (
    <div className="flex flex-col items-start gap-1">
      <Badge tone={ACTION_TONE[rec.action] ?? "neutral"}>
        {ACTION_LABELS[rec.action] ?? rec.action}
      </Badge>
      {rec.approved_limit_paise !== null ? (
        <span className="text-xs text-muted">
          {formatPaise(rec.approved_limit_paise)}
          {rec.band ? ` · band ${rec.band}` : ""}
        </span>
      ) : null}
      {row.change ? <ChangeBadge change={row.change} /> : null}
    </div>
  );
}

/** The compact card list for narrow viewports (mounted alone below md). */
function QueueCards({
  rows,
  loading,
  onOpen,
}: Pick<QueueTableProps, "rows" | "loading" | "onOpen">) {
  return (
    <div role="region" className="grid gap-2" aria-label="Cases awaiting review">
      {loading
        ? Array.from({ length: 6 }, (_, index) => (
            <div key={index} className="rounded border border-border bg-surface p-3">
              <Skeleton className="h-4 w-28" />
              <Skeleton className="mt-2 h-4 w-full" />
            </div>
          ))
        : rows.map((row) => (
            <button
              key={row.id}
              type="button"
              className="rounded border border-border bg-surface p-3 text-left transition-colors duration-fast hover:border-border-strong hover:bg-surface-subtle"
              onClick={() => onOpen(row, false)}
            >
              <span className="flex items-center justify-between gap-2">
                <strong className="text-ink">{row.applicant_name}</strong>
                <span className="text-xs text-muted">
                  {formatWaiting(row.waiting_seconds)}
                </span>
              </span>
              <span className="mt-1 block text-sm text-muted">
                {row.routed_because.text} ·{" "}
                {ACTION_LABELS[row.recommendation.action] ?? row.recommendation.action}
              </span>
            </button>
          ))}
    </div>
  );
}

/** The dense work table. Second visible column is ROUTED BECAUSE by design — it is
 * the column that tells the analyst what kind of case this is before opening it. */
export function QueueTable({ rows, loading, sort, onSort, onOpen }: QueueTableProps) {
  const rowRefs = useRef<(HTMLTableRowElement | null)[]>([]);
  const focusedIndex = useRef(0);
  // Mount exactly one layout — never both — so a screen reader hears one list.
  // Defaults to the table when matchMedia is unavailable (jsdom).
  const isDesktop = useMediaQuery("(min-width: 768px)", true);

  function focusRow(index: number): void {
    const clamped = Math.max(0, Math.min(index, rows.length - 1));
    focusedIndex.current = clamped;
    rowRefs.current[clamped]?.focus();
  }

  // j/k move the cursor; Enter opens. Handled at the region level so the keys work
  // wherever focus sits within the table body.
  function onRegionKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    if (event.key === "j") {
      event.preventDefault();
      focusRow(focusedIndex.current + 1);
    } else if (event.key === "k") {
      event.preventDefault();
      focusRow(focusedIndex.current - 1);
    }
  }

  function onRowClick(row: QueueRow, event: MouseEvent<HTMLTableRowElement>): void {
    onOpen(row, event.metaKey || event.ctrlKey);
  }

  function onRowKeyDown(row: QueueRow, event: KeyboardEvent<HTMLTableRowElement>): void {
    if (event.key === "Enter") {
      event.preventDefault();
      onOpen(row, false);
    }
  }

  if (!isDesktop) {
    return <QueueCards rows={rows} loading={loading} onOpen={onOpen} />;
  }

  return (
    <div
      className="w-full overflow-auto rounded border border-border bg-surface scrollbar-slim"
      onKeyDown={onRegionKeyDown}
    >
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">Cases awaiting review</caption>
        <colgroup>
          {COLUMNS.map((column) => (
            <col key={column.key} style={{ width: column.width }} />
          ))}
        </colgroup>
        <thead className="sticky top-0 z-10 bg-sunken">
          <tr>
            {COLUMNS.map((column) => {
              const direction = sortDirection(column, sort);
              return (
                <th
                  key={column.key}
                  scope="col"
                  aria-sort={direction}
                  // Eyebrow sizing/spacing without a CSS text-transform, so the
                  // literal header text stays the accessible name pinned by tests.
                  className={cn(
                    "h-9 border-b border-border px-3 text-eyebrow font-semibold text-muted",
                    column.numeric ? "text-right" : "text-left",
                    column.responsive,
                  )}
                >
                  {column.sortBase ? (
                    <button
                      type="button"
                      onClick={() => onSort(column.sortBase as string)}
                      className={cn(
                        "inline-flex items-center gap-1 font-semibold text-muted hover:text-ink",
                        column.numeric ? "flex-row-reverse" : "",
                      )}
                    >
                      {column.header}
                      <SortArrow direction={direction ?? "none"} />
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {loading
            ? Array.from({ length: 8 }).map((_, rowIndex) => (
                <tr key={rowIndex} className="border-b border-border">
                  {COLUMNS.map((column) => (
                    <td
                      key={column.key}
                      className={cn("h-row px-3", column.numeric ? "text-right" : "text-left", column.responsive)}
                    >
                      <Skeleton className={cn("h-4", column.numeric ? "ml-auto w-10" : "w-28")} />
                    </td>
                  ))}
                </tr>
              ))
            : rows.map((row, index) => (
                <tr
                  key={row.id}
                  ref={(element) => {
                    rowRefs.current[index] = element;
                  }}
                  tabIndex={0}
                  onFocus={() => {
                    focusedIndex.current = index;
                  }}
                  onClick={(event) => onRowClick(row, event)}
                  onKeyDown={(event) => onRowKeyDown(row, event)}
                  className={cn(
                    "cursor-pointer border-b border-border last:border-b-0",
                    "hover:bg-surface-subtle focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent",
                  )}
                >
                  <td className="h-row px-3 text-ink">
                    <ApplicantCell row={row} />
                  </td>
                  <td className="hidden h-row px-3 text-right tabular-nums xl:table-cell">
                    {row.amount_paise === null ? (
                      <>
                        <span aria-hidden="true" className="text-muted">—</span>
                        <span className="sr-only">Unavailable from system</span>
                      </>
                    ) : (
                      formatPaise(row.amount_paise)
                    )}
                  </td>
                  <td className="hidden h-row px-3 xl:table-cell">
                    {/* The queue endpoint does not carry source mix — mark it
                        explicitly unavailable rather than inventing a value. */}
                    <span aria-hidden="true" className="text-muted">—</span>
                    <span className="sr-only">
                      Source mix is not available in the queue view
                    </span>
                  </td>
                  <td className="h-row px-3 text-ink">
                    <span
                      className="line-clamp-2"
                      title={row.routed_because.text}
                    >
                      {row.routed_because.text}
                    </span>
                  </td>
                  <td className="h-row px-3 text-ink">
                    <RecommendationCell row={row} />
                  </td>
                  <td className="h-row px-3 text-right tabular-nums">
                    <MetricValue value={row.pd.value} status={row.pd.status} precision={3} />
                  </td>
                  <td className="h-row px-3 text-right tabular-nums">
                    <MetricValue
                      value={row.coverage.value}
                      status={row.coverage.status}
                      precision={0}
                    />
                  </td>
                  <td className="hidden h-row px-3 xl:table-cell">
                    <StatusDot
                      tone={VERIFICATION_TONE[row.verification] ?? "neutral"}
                      label={row.verification === "UNKNOWN" ? "Unknown" : row.verification}
                    />
                  </td>
                  <td className="h-row px-3 text-right tabular-nums text-ink">
                    {formatWaiting(row.waiting_seconds)}
                  </td>
                </tr>
              ))}
        </tbody>
      </table>
    </div>
  );
}
