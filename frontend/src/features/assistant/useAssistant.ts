import { useMutation, type UseMutationResult } from "@tanstack/react-query";

import { ApiError, api } from "../../lib/api";

// --------------------------------------------------------------------------- #
// Contracts, mirrored from backend/app/services/assistant/*.py. Both assistants
// are grounded and read-only: they phrase only over facts/maps the server hands
// the model and attach real citations, degrading to deterministic output when the
// LLM is disabled (used_llm=false).
// --------------------------------------------------------------------------- #
export interface ExplainCitation {
  label: string;
  detail: string;
  tab: string;
}

export interface DecisionExplanation {
  answer: string;
  citations: ExplainCitation[];
  used_llm: boolean;
}

export interface ArchCitation {
  title: string;
  paths: string[];
}

export interface ArchitectureAnswer {
  answer: string;
  citations: ArchCitation[];
  used_llm: boolean;
}

/** Ask "why was this decided?" — grounded in the case's real facts. */
export function useExplainDecision(
  applicationId: string,
): UseMutationResult<DecisionExplanation, ApiError, string> {
  return useMutation<DecisionExplanation, ApiError, string>({
    mutationFn: (question) =>
      api.post<DecisionExplanation>(`/api/v1/cases/${applicationId}/explain`, { question }),
  });
}

/** Ask "where in the repo is X?" — grounded in a curated, real-path map. */
export function useAskArchitecture(): UseMutationResult<ArchitectureAnswer, ApiError, string> {
  return useMutation<ArchitectureAnswer, ApiError, string>({
    mutationFn: (question) =>
      api.post<ArchitectureAnswer>(`/api/v1/architecture/ask`, { question }),
  });
}

/** A small, on-brand badge telling the user whether the answer was phrased by the
 * LLM or produced deterministically. Either way the facts and citations are real. */
export const SOURCE_NOTE = {
  llm: "AI-phrased over grounded facts — citations are real",
  deterministic: "Grounded summary (LLM off) — same facts, no phrasing model",
} as const;
