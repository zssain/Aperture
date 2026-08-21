import type { ReactNode } from "react";

import { cn } from "../../lib/cn";
import { Skeleton } from "./Skeleton";

export type SortDirection = "asc" | "desc";

export interface Column<T> {
  key: string;
  header: ReactNode;
  isNumeric?: boolean;
  /** Optional CSS width applied via <col> (an inline style, not a Tailwind value). */
  width?: string;
  sortable?: boolean;
  render: (row: T) => ReactNode;
}

export interface TableProps<T> {
  columns: Column<T>[];
  rows: T[];
  getRowId: (row: T) => string;
  caption: string;
  loading?: boolean;
  skeletonRows?: number;
  sort?: { key: string; direction: SortDirection };
  onSort?: (key: string) => void;
  className?: string;
}

/** Semantic data table: sticky header, right-aligned tabular numerics, aria-sort,
 * 44px rows, no zebra striping, and skeleton loading that preserves column widths. */
export function Table<T>({
  columns,
  rows,
  getRowId,
  caption,
  loading = false,
  skeletonRows = 6,
  sort,
  onSort,
  className,
}: TableProps<T>) {
  return (
    <div
      className={cn(
        "w-full overflow-auto rounded border border-border bg-surface",
        className,
      )}
    >
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">{caption}</caption>
        <colgroup>
          {columns.map((column) => (
            <col
              key={column.key}
              style={column.width ? { width: column.width } : undefined}
            />
          ))}
        </colgroup>
        <thead className="sticky top-0 z-10 bg-sunken">
          <tr>
            {columns.map((column) => {
              const active = sort?.key === column.key;
              const ariaSort = column.sortable
                ? active
                  ? sort?.direction === "asc"
                    ? "ascending"
                    : "descending"
                  : "none"
                : undefined;
              return (
                <th
                  key={column.key}
                  scope="col"
                  aria-sort={ariaSort}
                  className={cn(
                    "h-row border-b border-border px-3 font-medium text-muted",
                    column.isNumeric ? "text-right" : "text-left",
                  )}
                >
                  {column.sortable && onSort ? (
                    <button
                      type="button"
                      onClick={() => onSort(column.key)}
                      className="font-medium text-muted hover:text-ink"
                    >
                      {column.header}
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
            ? Array.from({ length: skeletonRows }).map((_, rowIndex) => (
                <tr key={rowIndex} className="border-b border-border">
                  {columns.map((column) => (
                    <td
                      key={column.key}
                      className={cn(
                        "h-row px-3",
                        column.isNumeric ? "text-right" : "text-left",
                      )}
                    >
                      <Skeleton
                        className={cn("h-4", column.isNumeric ? "ml-auto w-12" : "w-24")}
                      />
                    </td>
                  ))}
                </tr>
              ))
            : rows.map((row) => (
                <tr
                  key={getRowId(row)}
                  className="border-b border-border last:border-b-0"
                >
                  {columns.map((column) => (
                    <td
                      key={column.key}
                      className={cn(
                        "h-row px-3 text-ink",
                        column.isNumeric ? "text-right tabular-nums" : "text-left",
                      )}
                    >
                      {column.render(row)}
                    </td>
                  ))}
                </tr>
              ))}
        </tbody>
      </table>
    </div>
  );
}
