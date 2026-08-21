import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { OfflineBanner } from "../../components/ui/OfflineBanner";
import { useOnlineStatus } from "../../hooks/useOnlineStatus";
import { useStaleCheck } from "../../hooks/useStaleCheck";
import { useSession } from "../auth/useSession";
import { QueueFilters } from "./QueueFilters";
import { QueueTable } from "./QueueTable";
import { QueueViewTabs } from "./QueueViewTabs";
import {
  EMPTY_FILTERS,
  describeFilters,
  filtersActive,
  filtersFromParams,
  loadSort,
  paramsFromState,
  saveSort,
  useQueue,
  type QueueFilterState,
  type QueueRow,
} from "./useQueue";

function toggleSort(current: string, base: string): string {
  const currentBase = current.replace(/^-/, "");
  if (currentBase !== base) return base; // new column, ascending
  return current.startsWith("-") ? base : `-${base}`;
}

export function QueuePage() {
  const { data: session } = useSession();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const urlView = searchParams.get("view") ?? "";
  const filters = useMemo(() => filtersFromParams(searchParams), [searchParams]);
  const userId = session?.userId ?? "anon";

  // Sort is per-user local state (localStorage), not URL. The tick makes the query key change
  // when the persisted sort changes.
  const [, setSortTick] = useState(0);
  const sort = loadSort(userId, urlView || "my-exceptions");

  const query = useQueue(urlView, filters, sort);
  const online = useOnlineStatus();
  useStaleCheck(query.refetch);
  const firstPage = query.data?.pages[0];
  // The server resolves the default view for the role; mirror it so tabs + sort key agree.
  const view = firstPage?.view ?? (urlView || "my-exceptions");

  const rows: QueueRow[] = useMemo(
    () => query.data?.pages.flatMap((page) => page.rows) ?? [],
    [query.data],
  );
  const counts = firstPage?.counts ?? {};
  const resolvedNote = useResolvedNote(rows, query.isFetching);

  // Pin the resolved view into the URL on first landing, so a pasted URL round-trips exactly.
  useEffect(() => {
    if (!urlView && firstPage?.view) {
      setSearchParams(paramsFromState(firstPage.view, filters), { replace: true });
    }
  }, [urlView, firstPage, filters, setSearchParams]);

  function onViewChange(next: string): void {
    setSearchParams(paramsFromState(next, EMPTY_FILTERS));
  }

  function onFiltersChange(next: QueueFilterState): void {
    setSearchParams(paramsFromState(view, next));
  }

  function onSort(base: string): void {
    const next = toggleSort(loadSort(userId, view), base);
    saveSort(userId, view, next);
    setSortTick((tick) => tick + 1);
  }

  function onOpen(row: QueueRow, newTab: boolean): void {
    const path = `/cases/${row.application_id}`;
    if (newTab) window.open(path, "_blank", "noopener");
    else navigate(path);
  }

  if (query.isError && !query.data) {
    return (
      <ErrorState
        title="Could not load the queue"
        message={query.error.message}
        correlationId={query.error.correlationId}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const loading = query.isLoading;
  const active = filtersActive(filters);
  const resultLabel = `${rows.length} result${rows.length === 1 ? "" : "s"}`;

  return (
    <div className="flex flex-col gap-4">
      {!online ? <OfflineBanner /> : null}
      {query.isError ? (
        <ErrorState
          title="Could not refresh the queue"
          message={`${query.error.message} The previously loaded cases remain available below.`}
          correlationId={query.error.correlationId}
          onRetry={() => void query.refetch()}
          className="p-4"
        />
      ) : null}
      {Object.keys(counts).length > 0 ? (
        <QueueViewTabs counts={counts} view={view} onViewChange={onViewChange} />
      ) : null}

      <QueueFilters filters={filters} onChange={onFiltersChange} />

      {/* A filtered result count, announced politely for screen-reader users. */}
      <div aria-live="polite" className="sr-only">
        {loading ? "Loading" : resultLabel}
      </div>

      {resolvedNote ? (
        <p role="status" className="text-sm text-muted">
          {resolvedNote}
        </p>
      ) : null}

      {!loading && rows.length === 0 ? (
        active ? (
          <EmptyState
            title="No cases match these filters"
            description={`Active: ${describeFilters(filters).join(", ")}.`}
            action={
              <Button variant="secondary" size="sm" onClick={() => onFiltersChange(EMPTY_FILTERS)}>
                Clear filters
              </Button>
            }
          />
        ) : (
          <EmptyState
            title="Nothing needs review"
            description={`${firstPage?.auto_decided_24h ?? 0} decisions were made automatically in the last 24 hours.`}
            action={
              <Button variant="secondary" size="sm" onClick={() => onViewChange("all-decisions")}>
                View all decisions
              </Button>
            }
          />
        )
      ) : (
        <QueueTable rows={rows} loading={loading} sort={sort} onSort={onSort} onOpen={onOpen} />
      )}

      {query.hasNextPage ? (
        <div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void query.fetchNextPage()}
            disabled={query.isFetchingNextPage}
          >
            {query.isFetchingNextPage ? "Loading…" : "Load more"}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

/** Detect cases that vanished on a refetch (resolved elsewhere) and describe them once. */
function useResolvedNote(rows: QueueRow[], isFetching: boolean): string | null {
  const prevIds = useRef<Set<string>>(new Set());
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    if (isFetching) return;
    const currentIds = new Set(rows.map((row) => row.id));
    const removed = [...prevIds.current].filter((id) => !currentIds.has(id));
    if (prevIds.current.size > 0 && removed.length > 0 && currentIds.size > 0) {
      const count = removed.length;
      setNote(`${count} case${count === 1 ? "" : "s"} left the queue (resolved elsewhere).`);
    }
    prevIds.current = currentIds;
  }, [rows, isFetching]);

  return note;
}
