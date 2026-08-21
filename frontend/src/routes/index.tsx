import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "../components/shell/AppShell";
import { RequireAuth } from "../components/shell/RequireAuth";
import { RequireRole } from "../components/shell/RequireRole";
import { EmptyState } from "../components/ui/EmptyState";
import { SignInPage } from "../features/auth/SignInPage";
import { CaseFilePage } from "../features/case/CaseFilePage";
import { IngestPage } from "../features/ingest/IngestPage";
import { QueuePage } from "../features/queue/QueuePage";
import { PolicyStudioPage } from "../features/policy/PolicyStudioPage";
import { HealthPage } from "../features/health/HealthPage";

interface NotFoundPageProps {
  title: string;
  description: string;
}

function NotFoundPage({ title, description }: NotFoundPageProps) {
  return <EmptyState title={title} description={description} />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/signin" element={<SignInPage />} />

      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/queue" replace />} />
        <Route path="/queue" element={<QueuePage />} />
        <Route path="/cases/:id" element={<CaseFilePage />} />
        <Route
          path="/ingest"
          element={
            <RequireRole roles={["CREDIT_ANALYST", "CREDIT_POLICY_OWNER"]}>
              <IngestPage />
            </RequireRole>
          }
        />
        <Route
          path="/policy"
          element={
            <RequireRole roles={["CREDIT_POLICY_OWNER"]}>
              <PolicyStudioPage />
            </RequireRole>
          }
        />
        <Route
          path="/health"
          element={
            <RequireRole roles={["CREDIT_POLICY_OWNER", "AUDITOR"]}>
              <HealthPage />
            </RequireRole>
          }
        />
      </Route>

      <Route
        path="*"
        element={
          <NotFoundPage
            title="Page not found"
            description="The page you requested does not exist."
          />
        }
      />
    </Routes>
  );
}
