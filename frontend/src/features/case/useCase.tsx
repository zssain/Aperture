import {
  useInfiniteQuery,
  useQuery,
  type UseInfiniteQueryResult,
  type UseQueryResult,
} from "@tanstack/react-query";
import { createContext, useContext, type ReactNode } from "react";

import { cn } from "../../lib/cn";
import { ApiError, api } from "../../lib/api";
import type { MetricStatus } from "../queue/useQueue";

// --------------------------------------------------------------------------- #
// Contract, mirrored from backend/app/schemas/case.py.
// --------------------------------------------------------------------------- #
export interface Metric {
  value: number | null;
  status: MetricStatus;
}

export interface CaseApplication {
  id: string;
  status: string;
  product: string | null;
  requested_amount_paise: number | null;
  requested_tenor_months: number | null;
  created_at: string;
}

export interface CaseApplicant {
  id: string;
  external_ref: string;
  display_name: string | null;
  phone: string | null;
}

export interface CaseSource {
  id: string;
  source_type: string;
  tier: string | null;
  status: string;
  provider: string | null;
  period_start: string | null;
  period_end: string | null;
  last_sync_at: string | null;
  freshness_days: number | null;
}

export interface CaseReason {
  code: string;
  message: string;
  polarity: string;
  template_params: Record<string, unknown>;
  order: number;
}

export interface CaseDecision {
  id: string;
  action: string;
  routing: string;
  outcome: string;
  policy_version: string | null;
  approved_limit_paise: number | null;
  terms: Record<string, unknown>;
  fired_rules: Array<Record<string, unknown>>;
  exploration_cohort: boolean;
  is_final: boolean;
  decided_at: string;
  reasons: CaseReason[];
  resolved: boolean;
}

export interface Contribution {
  feature: string;
  value?: number | null;
  contribution: number;
  direction?: string;
  present?: boolean;
}

export interface RiskPayload {
  pd: number | null;
  calibration_status: string;
  model_version: string;
  feature_schema_version: string;
  contributions: Contribution[];
  reason_codes: string[];
}

export interface CoverageComponent {
  name: string;
  weight: number;
  fraction: number;
  contribution: number;
  detail: string;
}

export interface CoverageMissingSource {
  source_type: string;
  why: string;
  coverage_delta: number;
}

export interface CoveragePayload {
  score: number;
  band: string;
  weights_version: string;
  components: CoverageComponent[];
  missing_sources: CoverageMissingSource[];
}

export interface AffordabilityPayload {
  status: string;
  income_basis: string;
  net_monthly_income_paise: number | null;
  recurring_obligations_paise: number;
  essential_expenses_paise: number;
  disposable_income_paise: number | null;
  new_emi_paise: number | null;
  existing_emi_paise: number;
  dsr: number | null;
  dsr_ceiling: number;
  max_supportable_principal_paise: number | null;
}

export interface Assessment {
  kind: string;
  engine_version: string;
  model_version: string | null;
  calibration_status: string;
  payload: Record<string, unknown>;
}

export interface CitedEvent {
  id: string;
  occurred_at: string;
  direction: string | null;
  amount_paise: number | null;
  balance_paise: number | null;
  description: string | null;
}

export interface ManipulationFinding {
  detector_id: string;
  severity: string;
  statement: string;
  cited_event_ids: string[];
  confidence: number;
  values: Record<string, unknown>;
  cited_events: CitedEvent[];
}

export interface RecourseOption {
  rank: number;
  description: string;
  required_change: Record<string, unknown>;
  projected_action: string | null;
  projected_limit_paise: number | null;
  verified: boolean;
}

export interface CaseReview {
  id: string;
  queue: string;
  status: string;
  outcome: string | null;
  reason_code: string | null;
  reason_text: string | null;
  assigned_at: string | null;
  resolved_at: string | null;
}

export interface Chips {
  pd: Metric;
  coverage: { score: number | null; band: string | null; status: MetricStatus };
  affordability: { status: string; headroom_paise: number | null };
  verification: string;
}

export interface Counterfactual {
  available: boolean;
  outcome: string;
  action: string | null;
  note: string;
}

export interface CaseData {
  application: CaseApplication;
  applicant: CaseApplicant;
  case_age_seconds: number;
  consent_status: string | null;
  stale: { is_stale: boolean; new_event_count: number };
  feature_snapshot_id: string | null;
  sources: CaseSource[];
  decision: CaseDecision | null;
  assessments: Record<string, Assessment>;
  assessment_failed: boolean;
  chips: Chips;
  manipulation_findings: ManipulationFinding[];
  recourse: RecourseOption[];
  reviews: CaseReview[];
  blocking_tab: string;
  bureau_only: Counterfactual;
}

export interface EvidenceEvent {
  id: string;
  occurred_at: string;
  direction: string | null;
  amount_paise: number | null;
  balance_paise: number | null;
  description: string | null;
  category: string;
  confidence: number;
  classification_method?: "RULE" | "VECTOR_KNN" | "UNCLASSIFIED";
  classifier_version?: string;
  catalog_version_id?: string | null;
  matched_entry_id?: string | null;
  match_similarity?: number | null;
}

export interface EvidencePage {
  rows: EvidenceEvent[];
  next_cursor: string | null;
}

export interface Lineage {
  feature_key: string;
  version: string;
  dtype: string;
  window: string;
  formula_doc: string;
  null_policy: string;
  monotonic_direction: string;
  value: number | null;
  null_reason: string | null;
  contributing_event_ids: string[];
  recomputed_value: number | null;
  matches: boolean;
}

// --------------------------------------------------------------------------- #
// Tabs — the case opens on blocking_tab, not the first tab.
// --------------------------------------------------------------------------- #
export const TABS: readonly string[] = [
  "evidence",
  "assessment",
  "verification",
  "recourse",
  "decision",
];

export const TAB_LABELS: Record<string, string> = {
  evidence: "Evidence",
  assessment: "Assessment",
  verification: "Verification",
  recourse: "Recourse",
  decision: "Decision & Audit",
};

// --------------------------------------------------------------------------- #
// Queries.
// --------------------------------------------------------------------------- #
export function useCase(applicationId: string): UseQueryResult<CaseData, ApiError> {
  return useQuery<CaseData, ApiError>({
    queryKey: ["case", applicationId],
    queryFn: () => api.get<CaseData>(`/api/v1/cases/${applicationId}`),
    staleTime: 10_000,
    retry: false,
  });
}

export function useEvidence(
  applicationId: string,
  category: string,
): UseInfiniteQueryResult<{ pages: EvidencePage[]; pageParams: unknown[] }, ApiError> {
  return useInfiniteQuery<
    EvidencePage,
    ApiError,
    { pages: EvidencePage[]; pageParams: unknown[] },
    unknown[],
    string | undefined
  >({
    queryKey: ["case-evidence", applicationId, category],
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams();
      if (category) params.set("category", category);
      if (pageParam) params.set("cursor", pageParam);
      params.set("limit", "25");
      return api.get<EvidencePage>(
        `/api/v1/cases/${applicationId}/evidence?${params.toString()}`,
      );
    },
    initialPageParam: undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    staleTime: 10_000,
  });
}

export function useLineage(
  snapshotId: string | null,
  featureKey: string | null,
): UseQueryResult<Lineage, ApiError> {
  return useQuery<Lineage, ApiError>({
    queryKey: ["lineage", snapshotId, featureKey],
    queryFn: () => api.get<Lineage>(`/api/v1/features/${snapshotId}/${featureKey}/lineage`),
    enabled: Boolean(snapshotId && featureKey),
    retry: false,
  });
}

// --------------------------------------------------------------------------- #
// The drawer is opened by clicking any number anywhere; state lives in the URL. Rather than
// thread a callback through every component, expose it via context.
// --------------------------------------------------------------------------- #
export interface FeatureDrawerApi {
  open: (featureKey: string) => void;
}

export const FeatureDrawerContext = createContext<FeatureDrawerApi>({ open: () => undefined });

export function useFeatureDrawer(): FeatureDrawerApi {
  return useContext(FeatureDrawerContext);
}

/** A number that is a click from its source: opens the evidence drawer on its feature.
 * The number itself must still be rendered with MetricValue where it is an assessment
 * number (invariant 8) — this only wraps it in an affordance. */
export function FeatureNumber({
  featureKey,
  children,
  className,
}: {
  featureKey: string;
  children: ReactNode;
  className?: string;
}) {
  const { open } = useFeatureDrawer();
  return (
    <button
      type="button"
      onClick={() => open(featureKey)}
      className={cn(
        "rounded underline decoration-dotted decoration-muted underline-offset-4",
        "hover:decoration-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-accent",
        className,
      )}
    >
      {children}
    </button>
  );
}
