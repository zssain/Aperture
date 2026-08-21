import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import { ApiError, api } from "../../lib/api";

// --------------------------------------------------------------------------- #
// Review + audit contract, mirrored from the backend.
// --------------------------------------------------------------------------- #
export type ReviewAction = "confirm" | "override" | "request_evidence";
export type ReviewOutcome = "APPROVED" | "DECLINED" | "ESCALATED";

export interface ReviewRequest {
  action: ReviewAction;
  reason_code?: string;
  reason_text?: string;
  override_outcome?: ReviewOutcome;
  language?: string;
}

export interface Notice {
  subject: string;
  body: string;
  language: string;
}

export interface ReviewResponse {
  review_id: string;
  status: string;
  resulting_outcome: string;
  recommendation_outcome: string;
  diverged: boolean;
  notice: Notice;
}

export interface LedgerItem {
  seq: number;
  event_type: string;
  actor_id: string | null;
  actor_email: string | null;
  payload: Record<string, unknown>;
  payload_hash: string;
  prev_hash: string;
  created_at: string;
}

export interface ReplayResult {
  status: "IDENTICAL" | "DIVERGED";
  diff: Record<string, { stored: unknown; recomputed: unknown }>;
  recomputed_outcome: string;
  recomputed_action: string;
  stored_action: string;
  policy_version_id: string;
  counterfactual: boolean;
  reused_risk: boolean;
}

/** Override reason codes. A required, explicit reason is what makes an override non-silent. */
export const REASON_CODES: ReadonlyArray<{ value: string; label: string }> = [
  { value: "DOCUMENT_REVIEW", label: "Documents reviewed manually" },
  { value: "POLICY_EXCEPTION", label: "Approved policy exception" },
  { value: "SUSPECTED_FRAUD", label: "Suspected fraud / manipulation" },
  { value: "AFFORDABILITY_CONCERN", label: "Affordability concern" },
  { value: "ADDITIONAL_CONTEXT", label: "Additional applicant context" },
  { value: "DATA_QUALITY", label: "Evidence quality issue" },
];

export const MIN_REASON_LENGTH = 20;

// --------------------------------------------------------------------------- #
// Hooks.
// --------------------------------------------------------------------------- #
export function useDecisionLedger(
  decisionId: string | null,
): UseQueryResult<LedgerItem[], ApiError> {
  return useQuery<LedgerItem[], ApiError>({
    queryKey: ["decision-ledger", decisionId],
    queryFn: () => api.get<LedgerItem[]>(`/api/v1/decisions/${decisionId}/ledger`),
    enabled: Boolean(decisionId),
    retry: false,
  });
}

export function useSubmitReview(
  decisionId: string,
  applicationId: string,
): UseMutationResult<ReviewResponse, ApiError, ReviewRequest> {
  const queryClient = useQueryClient();
  return useMutation<ReviewResponse, ApiError, ReviewRequest>({
    mutationFn: (body) => api.post<ReviewResponse>(`/api/v1/decisions/${decisionId}/review`, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["case", applicationId] });
      void queryClient.invalidateQueries({ queryKey: ["decision-ledger", decisionId] });
    },
  });
}

export function useReplay(
  decisionId: string,
): UseMutationResult<ReplayResult, ApiError, void> {
  return useMutation<ReplayResult, ApiError, void>({
    mutationFn: () => api.post<ReplayResult>(`/api/v1/decisions/${decisionId}/replay`, {}),
  });
}

export function useNoticePreview(
  decisionId: string | null,
  kind: "decision" | "recourse",
  language: string,
): UseQueryResult<Notice, ApiError> {
  return useQuery<Notice, ApiError>({
    queryKey: ["notice-preview", decisionId, kind, language],
    queryFn: () =>
      api.get<Notice>(
        `/api/v1/decisions/${decisionId}/notice/preview?kind=${kind}&language=${language}`,
      ),
    enabled: Boolean(decisionId),
    retry: false,
  });
}

export function useSendRecourse(
  decisionId: string,
): UseMutationResult<Notice, ApiError, { language: string }> {
  return useMutation<Notice, ApiError, { language: string }>({
    mutationFn: (body) => api.post<Notice>(`/api/v1/decisions/${decisionId}/recourse/send`, body),
  });
}
