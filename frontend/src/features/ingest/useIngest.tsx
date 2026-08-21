import { useMutation, useQuery } from "@tanstack/react-query";
import type { UseMutationResult, UseQueryResult } from "@tanstack/react-query";

import { ApiError, api } from "../../lib/api";

export interface ApplicantValues {
  displayName: string;
  externalRef: string;
  declaredIncomeRupees: string;
  occupation: string;
  requestedAmountRupees: string;
  requestedTenorMonths: string;
}

export type SourceType = "BANK" | "UPI";

export interface IngestionResult {
  status: string;
  snapshot_id: string | null;
  tier: string | null;
  already_ingested: boolean;
  ingested: number;
  deduplicated: number;
  rejected: number;
  rejected_reasons: Array<{ row?: number; reason?: string }>;
  provenance: Array<Record<string, unknown>>;
}

export interface CaseIntake {
  status: string;
  already_ingested: boolean;
  application_id: string;
  applicant_id: string;
  application_status: string;
  job_id: string | null;
  ingestion: IngestionResult | null;
  existing_case_url: string | null;
}

export type PipelineStageStatus = "pending" | "running" | "complete" | "failed";

export interface PipelineStage {
  key: string;
  label: string;
  status: PipelineStageStatus;
  count?: number | null;
  message?: string | null;
  started_at?: string;
  finished_at?: string;
}

export interface PipelineSource {
  connection_id: string;
  source_type?: string;
  status: string;
  ingested?: number;
  deduplicated?: number;
  message?: string | null;
}

export interface PipelineResult {
  application_id?: string;
  decision_id?: string;
  outcome?: string;
  retryable_stage?: string | null;
  started_at?: string;
  stages?: PipelineStage[];
  sources?: PipelineSource[];
}

export interface PipelineJob {
  id: string;
  job_type: string;
  status: "PENDING" | "RUNNING" | "SUCCEEDED" | "FAILED" | "DEAD";
  attempts: number;
  max_attempts: number;
  result: PipelineResult | null;
  error: string | null;
}

interface ConnectInput {
  applicant: ApplicantValues;
  consentGranted: boolean;
  purpose: string;
  scopes: SourceType[];
  expiresAt: string | null;
  failureModes?: Partial<Record<SourceType, "timeout" | "error" | "partial">>;
}

interface UploadInput {
  applicant: ApplicantValues;
  file: File;
}

function wholeNumber(value: string): number {
  return Number.parseInt(value, 10);
}

function toPaise(rupees: string): number {
  return wholeNumber(rupees) * 100;
}

function fields(applicant: ApplicantValues) {
  return {
    display_name: applicant.displayName.trim(),
    external_ref: applicant.externalRef.trim(),
    declared_income_paise: toPaise(applicant.declaredIncomeRupees),
    occupation: applicant.occupation,
    requested_amount_paise: toPaise(applicant.requestedAmountRupees),
    requested_tenor_months: wholeNumber(applicant.requestedTenorMonths),
    product: "PERSONAL_LOAN",
  };
}

export function useCreateConnectCase(): UseMutationResult<CaseIntake, ApiError, ConnectInput> {
  return useMutation<CaseIntake, ApiError, ConnectInput>({
    mutationFn: ({ applicant, consentGranted, purpose, scopes, expiresAt, failureModes }) =>
      api.post<CaseIntake>("/api/v1/applications", {
        ...fields(applicant),
        consent_granted: consentGranted,
        purpose,
        scope: consentGranted ? scopes : [],
        expires_at: consentGranted && expiresAt ? expiresAt : null,
        failure_modes: failureModes ?? {},
      }),
  });
}

export function useCreateDocumentCase(): UseMutationResult<CaseIntake, ApiError, UploadInput> {
  return useMutation<CaseIntake, ApiError, UploadInput>({
    mutationFn: ({ applicant, file }) => {
      const form = new FormData();
      const values = fields(applicant);
      for (const [key, value] of Object.entries(values)) form.set(key, String(value));
      form.set("file", file);
      return api.upload<CaseIntake>("/api/v1/applications/documents", form);
    },
  });
}

export function usePipelineJob(jobId: string | null): UseQueryResult<PipelineJob, ApiError> {
  return useQuery<PipelineJob, ApiError>({
    queryKey: ["ingest-job", jobId],
    queryFn: () => api.get<PipelineJob>(`/api/v1/jobs/${jobId}`),
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "SUCCEEDED" || status === "DEAD" ? false : 750;
    },
    refetchIntervalInBackground: true,
  });
}

interface RetryInput {
  jobId: string;
  stage: string;
}

export function useRetryPipeline(): UseMutationResult<PipelineJob, ApiError, RetryInput> {
  return useMutation<PipelineJob, ApiError, RetryInput>({
    mutationFn: ({ jobId, stage }) =>
      api.post<PipelineJob>(`/api/v1/jobs/${jobId}/retry`, { stage }),
  });
}
