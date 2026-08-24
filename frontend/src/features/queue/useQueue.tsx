import {
  useInfiniteQuery,
  type UseInfiniteQueryResult,
} from "@tanstack/react-query";

import { ApiError, api } from "../../lib/api";

// --------------------------------------------------------------------------- #
// The response contract, mirrored from the backend queue schema.
// --------------------------------------------------------------------------- #
export type MetricStatus = "measured" | "uncalibrated" | "unavailable";

export interface Metric {
  value: number | null;
  status: MetricStatus;
}

export interface RoutedBecause {
  text: string;
  rule_number: number;
}

export interface Recommendation {
  action: string;
  band: string | null;
  approved_limit_paise: number | null;
  tenor_months: number | null;
  annual_rate_bps: number | null;
}

export interface QueueChange {
  direction: "IMPROVED" | "WORSENED" | "UNCHANGED";
  previous_band: string;
  new_band: string;
  previous_outcome: string;
  new_outcome: string;
  human_action_protected: boolean;
}

export interface QueueRow {
  id: string;
  application_id: string;
  applicant_name: string;
  applicant_ref: string;
  amount_paise: number | null;
  routed_because: RoutedBecause;
  recommendation: Recommendation;
  pd: Metric;
  coverage: Metric;
  verification: string;
  waiting_seconds: number;
  decided_at: string;
  superseded?: boolean;
  change?: QueueChange | null;
}

export interface QueuePage {
  view: string;
  counts: Record<string, number>;
  rows: QueueRow[];
  next_cursor: string | null;
  auto_decided_24h: number;
}

// --------------------------------------------------------------------------- #
// View ordering + labels. The set of *visible* tabs comes from the response counts
// (a view the role cannot access is simply absent), ordered canonically here.
// --------------------------------------------------------------------------- #
export const VIEW_ORDER: readonly string[] = [
  "my-exceptions",
  "fraud-review",
  "evidence-needed",
  "newly-eligible",
  "deterioration",
  "all-decisions",
  "qa-sample",
];

export const VIEW_LABELS: Record<string, string> = {
  "my-exceptions": "My exceptions",
  "fraud-review": "Fraud review",
  "evidence-needed": "Evidence needed",
  "newly-eligible": "Newly eligible",
  "deterioration": "Deterioration",
  "all-decisions": "All decisions",
  "qa-sample": "QA sample",
};

// --------------------------------------------------------------------------- #
// Filters. Kept as strings (the shape of the URL + the inputs); converted to typed
// query params only at the fetch edge.
// --------------------------------------------------------------------------- #
export interface QueueFilterState {
  q: string;
  band: string; // "" | CLEAR | ELEVATED | HIGH
  coverageMin: string;
  coverageMax: string;
  amountMin: string; // in rupees at the input; sent as paise
  amountMax: string;
  waitingGt: string; // hours
}

export const EMPTY_FILTERS: QueueFilterState = {
  q: "",
  band: "",
  coverageMin: "",
  coverageMax: "",
  amountMin: "",
  amountMax: "",
  waitingGt: "",
};

export function filtersActive(filters: QueueFilterState): boolean {
  return Object.values(filters).some((value) => value.trim() !== "");
}

/** Human phrases for the active filters, for the "no results" state. */
export function describeFilters(filters: QueueFilterState): string[] {
  const parts: string[] = [];
  if (filters.q.trim()) parts.push(`search "${filters.q.trim()}"`);
  if (filters.band) parts.push(`verification ${filters.band}`);
  if (filters.coverageMin) parts.push(`coverage ≥ ${filters.coverageMin}`);
  if (filters.coverageMax) parts.push(`coverage ≤ ${filters.coverageMax}`);
  if (filters.amountMin) parts.push(`amount ≥ ₹${filters.amountMin}`);
  if (filters.amountMax) parts.push(`amount ≤ ₹${filters.amountMax}`);
  if (filters.waitingGt) parts.push(`waiting > ${filters.waitingGt}h`);
  return parts;
}

// --------------------------------------------------------------------------- #
// URL <-> filter state. View + filters live in the URL so a view is shareable; sort is
// per-user and lives in localStorage instead.
// --------------------------------------------------------------------------- #
export function filtersFromParams(params: URLSearchParams): QueueFilterState {
  return {
    q: params.get("q") ?? "",
    band: params.get("band") ?? "",
    coverageMin: params.get("cmin") ?? "",
    coverageMax: params.get("cmax") ?? "",
    amountMin: params.get("amin") ?? "",
    amountMax: params.get("amax") ?? "",
    waitingGt: params.get("wait") ?? "",
  };
}

/** Build the next URLSearchParams from a view + filters (omitting empty values). */
export function paramsFromState(view: string, filters: QueueFilterState): URLSearchParams {
  const next = new URLSearchParams();
  next.set("view", view);
  const map: Array<[string, string]> = [
    ["q", filters.q],
    ["band", filters.band],
    ["cmin", filters.coverageMin],
    ["cmax", filters.coverageMax],
    ["amin", filters.amountMin],
    ["amax", filters.amountMax],
    ["wait", filters.waitingGt],
  ];
  for (const [key, value] of map) {
    if (value.trim() !== "") next.set(key, value.trim());
  }
  return next;
}

// --------------------------------------------------------------------------- #
// Sort persistence (per view, per user).
// --------------------------------------------------------------------------- #
export const SORTS: readonly string[] = [
  "waiting",
  "-waiting",
  "pd",
  "-pd",
  "coverage",
  "-coverage",
  "amount",
  "-amount",
];

export function sortStorageKey(userId: string, view: string): string {
  return `aperture:queue-sort:${userId}:${view}`;
}

// Pending exception queues surface the longest-waiting case first; the "all decisions" and
// QA-sample ledgers are a chronological record, so they default to newest-decided first.
export function defaultSort(view: string): string {
  return view === "all-decisions" || view === "qa-sample" ? "-waiting" : "waiting";
}

export function loadSort(userId: string, view: string): string {
  try {
    const stored = window.localStorage.getItem(sortStorageKey(userId, view));
    if (stored && SORTS.includes(stored)) return stored;
  } catch {
    // localStorage unavailable (private mode / SSR) — fall through to the default.
  }
  return defaultSort(view);
}

export function saveSort(userId: string, view: string, sort: string): void {
  try {
    window.localStorage.setItem(sortStorageKey(userId, view), sort);
  } catch {
    // Best-effort; a failed persist must never break navigation.
  }
}

// --------------------------------------------------------------------------- #
// The fetch + infinite query. Pagination is cursor-based (the backend never returns the
// full set); pages are appended as the analyst pages down.
// --------------------------------------------------------------------------- #
function buildQuery(
  view: string,
  filters: QueueFilterState,
  sort: string,
  cursor: string | undefined,
): string {
  const params = new URLSearchParams();
  params.set("view", view);
  params.set("sort", sort);
  if (filters.q.trim()) params.set("q", filters.q.trim());
  if (filters.band) params.set("band", filters.band);
  if (filters.coverageMin) params.set("coverage_min", filters.coverageMin);
  if (filters.coverageMax) params.set("coverage_max", filters.coverageMax);
  // Amount inputs are in rupees; the API works in integer paise (invariant 6).
  if (filters.amountMin) params.set("amount_min", String(Number(filters.amountMin) * 100));
  if (filters.amountMax) params.set("amount_max", String(Number(filters.amountMax) * 100));
  if (filters.waitingGt) params.set("waiting_gt", filters.waitingGt);
  if (cursor) params.set("cursor", cursor);
  return params.toString();
}

export function fetchQueuePage(
  view: string,
  filters: QueueFilterState,
  sort: string,
  cursor: string | undefined,
): Promise<QueuePage> {
  return api.get<QueuePage>(`/api/v1/queue?${buildQuery(view, filters, sort, cursor)}`);
}

export function useQueue(
  view: string,
  filters: QueueFilterState,
  sort: string,
): UseInfiniteQueryResult<{ pages: QueuePage[]; pageParams: unknown[] }, ApiError> {
  return useInfiniteQuery<
    QueuePage,
    ApiError,
    { pages: QueuePage[]; pageParams: unknown[] },
    unknown[],
    string | undefined
  >({
    queryKey: ["queue", view, filters, sort],
    queryFn: ({ pageParam }) => fetchQueuePage(view, filters, sort, pageParam),
    initialPageParam: undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    staleTime: 10_000,
  });
}
