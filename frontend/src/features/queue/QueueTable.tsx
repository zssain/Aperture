import type { KeyboardEvent, MouseEvent } from "react";
import { useRef } from "react";

import { Chip } from "../../components/ui/Chip";
import { MetricValue } from "../../components/ui/MetricValue";
import { Skeleton } from "../../components/ui/Skeleton";
import { StatusDot } from "../../components/ui/StatusDot";
import type { Tone } from "../../components/ui/tones";
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

function ariaSortFor(column: ColumnSpec, sort: string): "ascending" | "descending" | "none" | undefined {
  if (!column.sortBase) return undefined;
  const base = sort.replace(/^-/, "");
  if (base !== column.sortBase) return "none";
  return sort.startsWith("-") ? "descending" : "ascending";
}

function ApplicantCell({ row }: { row: QueueRow }) {
  return (
    <div className="flex flex-col">
      <span className="font-medium text-ink">{row.applicant_name}</span>
      <span className="text-xs text-muted">{row.applicant_ref}</span>
    </div>
  );
}

function RecommendationCell({ row }: { row: QueueRow }) {
  const rec = row.recommendation;
  return (
    <div className="flex flex-col">
      <span className="text-ink">{ACTION_LABELS[rec.action] ?? rec.action}</span>
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

/** The dense work table. Second column is ROUTED BECAUSE by design — it is the only column
 * that tells the analyst what kind of case this is before opening it. */
export function QueueTable({ rows, loading, sort, onSort, onOpen }: QueueTableProps) {
  const rowRefs = useRef<(HTMLTableRowElement | null)[]>([]);
  const focusedIndex = useRef(0);

  function focusRow(index: number): void {
    const clamped = Math.max(0, Math.min(index, rows.length - 1));
    focusedIndex.current = clamped;
    rowRefs.current[clamped]?.focus();
  }

  // j/k move the cursor; Enter opens. Handled at the region level so the keys work wherever
  // focus sits within the table body.
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
    // Cmd/Ctrl-click opens the case in a new tab, like a link.
    onOpen(row, event.metaKey || event.ctrlKey);
  }

  function onRowKeyDown(row: QueueRow, event: KeyboardEvent<HTMLTableRowElement>): void {
    if (event.key === "Enter") {
      event.preventDefault();
      onOpen(row, false);
    }
  }

  return (<>
    <div role="region" className="grid gap-2 md:hidden" aria-label="Cases awaiting review">
      {loading ? Array.from({ length: 6 }, (_, index) => <div key={index} className="rounded border border-border bg-surface p-3"><Skeleton className="h-4 w-28" /><Skeleton className="mt-2 h-4 w-full" /></div>) : rows.map((row) => <button key={row.id} className="rounded border border-border bg-surface p-3 text-left" onClick={() => onOpen(row, false)}><span className="flex justify-between"><strong>{row.applicant_name}</strong><span>{formatWaiting(row.waiting_seconds)}</span></span><span className="mt-1 block text-sm text-muted">{row.routed_because.text} · {ACTION_LABELS[row.recommendation.action] ?? row.recommendation.action}</span></button>)}
    </div>
    <div
      className="hidden w-full overflow-auto rounded border border-border bg-surface md:block"
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
            {COLUMNS.map((column) => (
              <th
                key={column.key}
                scope="col"
                aria-sort={ariaSortFor(column, sort)}
                className={cn(
                  "h-row border-b border-border px-3 font-medium text-muted",
                  column.numeric ? "text-right" : "text-left",
                  column.responsive,
                )}
              >
                {column.sortBase ? (
                  <button
                    type="button"
                    onClick={() => onSort(column.sortBase as string)}
                    className="font-medium text-muted hover:text-ink"
                  >
                    {column.header}
                  </button>
                ) : (
                  column.header
                )}
              </th>
            ))}
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
                    "hover:bg-sunken focus:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                  )}
                >
                  <td className="h-row px-3 text-ink">
                    <ApplicantCell row={row} />
                  </td>
                  <td className="hidden h-row px-3 text-right tabular-nums xl:table-cell">
                    {row.amount_paise === null ? <><span aria-hidden="true">—</span><span className="sr-only">Unavailable from system</span></> : formatPaise(row.amount_paise)}
                  </td>
                  <td className="hidden h-row px-3 xl:table-cell"><Chip tone="neutral">— system</Chip></td>
                  <td className="h-row px-3 text-ink">{row.routed_because.text}</td>
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
                    {row.verification === "UNKNOWN" ? (
                      <Chip tone="neutral">Unknown</Chip>
                    ) : (
                      <StatusDot
                        tone={VERIFICATION_TONE[row.verification] ?? "neutral"}
                        label={row.verification}
                      />
                    )}
                  </td>
                  <td className="h-row px-3 text-right tabular-nums text-ink">
                    {formatWaiting(row.waiting_seconds)}
                  </td>
                </tr>
              ))}
        </tbody>
      </table>
    </div>
  </>);
}
