import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { UseMutationResult, UseQueryResult } from "@tanstack/react-query";

import { ApiError, api } from "../../lib/api";

export type Role =
  | "CREDIT_ANALYST"
  | "FRAUD_REVIEWER"
  | "CREDIT_POLICY_OWNER"
  | "AUDITOR";

interface MeResponse {
  user_id: string;
  email: string;
  full_name: string;
  role: Role;
  tenant_id: string;
  tenant_name: string;
}

export interface Session {
  userId: string;
  email: string;
  fullName: string;
  role: Role;
  tenantId: string;
  tenantName: string;
}

export interface Credentials {
  email: string;
  password: string;
}

export const SESSION_QUERY_KEY = ["session"] as const;

const ROLE_LABELS: Record<Role, string> = {
  CREDIT_ANALYST: "Credit analyst",
  FRAUD_REVIEWER: "Fraud reviewer",
  CREDIT_POLICY_OWNER: "Policy owner",
  AUDITOR: "Auditor",
};

export function roleLabel(role: Role): string {
  return ROLE_LABELS[role];
}

function toSession(me: MeResponse): Session {
  return {
    userId: me.user_id,
    email: me.email,
    fullName: me.full_name,
    role: me.role,
    tenantId: me.tenant_id,
    tenantName: me.tenant_name,
  };
}

export function useSession(): UseQueryResult<Session | null, ApiError> {
  return useQuery<Session | null, ApiError>({
    queryKey: SESSION_QUERY_KEY,
    queryFn: async () => {
      try {
        const me = await api.get<MeResponse>("/api/v1/auth/me", {
          suppressUnauthorized: true,
        });
        return toSession(me);
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    staleTime: 60_000,
    retry: false,
  });
}

export function useSignIn(): UseMutationResult<Session, ApiError, Credentials> {
  const queryClient = useQueryClient();
  return useMutation<Session, ApiError, Credentials>({
    mutationFn: async (credentials) => {
      const me = await api.post<MeResponse>("/api/v1/auth/login", credentials);
      return toSession(me);
    },
    onSuccess: (session) => {
      queryClient.setQueryData(SESSION_QUERY_KEY, session);
    },
  });
}

export function useSignOut(): UseMutationResult<void, ApiError, void> {
  const queryClient = useQueryClient();
  return useMutation<void, ApiError, void>({
    mutationFn: async () => {
      await api.post<{ status: string }>("/api/v1/auth/logout");
    },
    onSuccess: () => {
      queryClient.setQueryData(SESSION_QUERY_KEY, null);
    },
  });
}
