import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { RenderResult } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";

import { SESSION_QUERY_KEY, type Session } from "../features/auth/useSession";

export interface RenderOptions {
  route?: string;
  /** When provided, seeds the session cache so no network probe runs. */
  session?: Session | null;
}

export function renderWithProviders(
  ui: ReactElement,
  options: RenderOptions = {},
): RenderResult {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  if (options.session !== undefined) {
    queryClient.setQueryData(SESSION_QUERY_KEY, options.session);
  }

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[options.route ?? "/"]}>
          {children}
        </MemoryRouter>
      </QueryClientProvider>
    );
  }

  return render(ui, { wrapper: Wrapper });
}

export const ANALYST_SESSION: Session = {
  userId: "00000000-0000-0000-0000-000000000001",
  email: "analyst@example.com",
  fullName: "Ana Analyst",
  role: "CREDIT_ANALYST",
  tenantId: "00000000-0000-0000-0000-0000000000aa",
  tenantName: "Acme Credit",
};
