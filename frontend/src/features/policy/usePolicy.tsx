import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../lib/api";

export interface Validation { ok: boolean; errors: string[] }
export interface PolicyVersion {
  id: string; version: number; status: "DRAFT" | "LIVE" | "ARCHIVED";
  rules: PolicyRules; author: string | null; change_note: string | null;
  published_at: string | null; draft_hash: string; validation: Validation;
}
export interface TermsBand {
  max_principal_paise: number; max_tenor_months: number; rate_band: string;
  annual_rate_bps: number; graduation?: Record<string, unknown> | null;
}
export interface PolicyRules {
  policy_version: string; min_coverage: number; pd_decline_threshold: number;
  pd_enhanced: number; pd_standard: number; cov_high: number; cov_mid: number;
  mandatory_review_ceiling_paise: number; exploration_margin: number;
  exploration_budget: number; terms: Record<string, TermsBand>;
}
export interface SimulationReport {
  job_id: string; status: string; draft_hash?: string; n_snapshots?: number;
  approval_delta?: number; cohort_deltas?: Record<string, { n: number; approval_delta: number }>;
  transition_matrix?: Record<string, number>; modelled_bad_rate_delta?: number;
  expected_loss_delta?: number; caveats?: string[];
  largest_flips?: Array<{ application_id: string; from: string; to: string }>;
}

export function usePolicies() {
  return useQuery({ queryKey: ["policies"], queryFn: () => api.get<PolicyVersion[]>("/api/v1/policies") });
}

export function useCreateDraft() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<PolicyVersion>("/api/v1/policies"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["policies"] }),
  });
}

export function useSaveDraft() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, rules }: { id: string; rules: PolicyRules }) =>
      api.patch<PolicyVersion>(`/api/v1/policies/${id}`, { rules }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["policies"] }),
  });
}

export function useStartSimulation() {
  return useMutation({
    mutationFn: (id: string) => api.post<{ job_id: string }>(`/api/v1/policies/${id}/simulate`),
  });
}

export function useSimulation(policyId: string | undefined, jobId: string | undefined) {
  return useQuery({
    queryKey: ["policy-simulation", policyId, jobId],
    queryFn: () => api.get<SimulationReport>(`/api/v1/policies/${policyId}/simulation/${jobId}`),
    enabled: Boolean(policyId && jobId),
    refetchInterval: (query) => query.state.data?.status === "SUCCEEDED" ? false : 1000,
  });
}

export function usePublish() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, simulationJobId, changeNote, bulk }: { id: string; simulationJobId: string; changeNote: string; bulk: boolean }) =>
      api.post(`/api/v1/policies/${id}/publish`, { simulation_job_id: simulationJobId, change_note: changeNote, bulk_redecide: bulk }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["policies"] }),
  });
}
