import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { Skeleton } from "../../components/ui/Skeleton";
import { OfflineBanner } from "../../components/ui/OfflineBanner";
import { useOnlineStatus } from "../../hooks/useOnlineStatus";
import { api } from "../../lib/api";
import { useSession } from "../auth/useSession";
import { AssessmentSummary } from "./AssessmentSummary";
import { CaseHeader } from "./CaseHeader";
import { CaseTabs } from "./CaseTabs";
import { ConfirmRecommendationModal } from "./ConfirmRecommendationModal";
import { DecisionSummary } from "./DecisionSummary";
import { EvidenceDrawer } from "./EvidenceDrawer";
import { OverrideModal, type OverrideSubmission } from "./OverrideModal";
import { AssessmentTab } from "./tabs/AssessmentTab";
import { DecisionAuditTab } from "./tabs/DecisionAuditTab";
import { EvidenceTab } from "./tabs/EvidenceTab";
import { RecourseTab } from "./tabs/RecourseTab";
import { VerificationTab } from "./tabs/VerificationTab";
import { FeatureDrawerContext, useCase, type CaseDecision } from "./useCase";
import { useSubmitReview } from "./useReview";

const FRAUD_OUTCOMES = new Set(["FRAUD_REVIEW", "REVIEW_FRAUD"]);

function Banner({ tone, children }: { tone: "warn" | "info"; children: React.ReactNode }) {
  const cls = tone === "warn" ? "border-negative text-negative" : "border-caution text-ink";
  return (
    <div role="status" className={`rounded border ${cls} bg-surface px-3 py-2 text-sm`}>
      {children}
    </div>
  );
}

function isFraudRouted(decision: CaseDecision): boolean {
  const gate = decision.fired_rules.find((r) => {
    const n = Number(r.number);
    return n >= 1 && n <= 9;
  });
  return gate ? FRAUD_OUTCOMES.has(String(gate.outcome)) : false;
}

export function CaseFilePage() {
  const { id } = useParams();
  const applicationId = id ?? "";
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const query = useCase(applicationId);
  const { data: session } = useSession();
  const online = useOnlineStatus();

  const data = query.data;
  const decisionId = data?.decision?.id ?? "";
  const submitReview = useSubmitReview(decisionId, applicationId);
  const redecide = useMutation({
    mutationFn: () => api.post(`/api/v1/applications/${applicationId}/decide`, {
      as_of: new Date().toISOString(),
      idempotency_key: `manual-redecision:${applicationId}:${Date.now()}`,
    }),
    onSuccess: () => { void query.refetch(); },
  });

  const urlTab = searchParams.get("tab");
  const feature = searchParams.get("feature");
  const activeTab = urlTab ?? data?.blocking_tab ?? "evidence";

  const [overrideOpen, setOverrideOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pendingReturn, setPendingReturn] = useState(false);
  const returnTimer = useRef<number | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!urlTab && data?.blocking_tab) {
      const next = new URLSearchParams(searchParams);
      next.set("tab", data.blocking_tab);
      setSearchParams(next, { replace: true });
    }
  }, [urlTab, data, searchParams, setSearchParams]);

  useEffect(() => () => {
    if (returnTimer.current) window.clearTimeout(returnTimer.current);
  }, []);

  function setParam(key: string, value: string | null): void {
    const next = new URLSearchParams(searchParams);
    if (value === null) next.delete(key);
    else next.set(key, value);
    setSearchParams(next);
  }

  function openFeature(featureKey: string): void {
    if (typeof document !== "undefined") {
      triggerRef.current = document.activeElement as HTMLElement | null;
    }
    setParam("feature", featureKey);
  }

  function closeFeature(): void {
    setParam("feature", null);
    const trigger = triggerRef.current;
    if (trigger) requestAnimationFrame(() => trigger.focus());
  }

  function afterReview(): void {
    void query.refetch();
    setPendingReturn(true);
    // Return to the queue after a moment, with an undo affordance for the transition.
    returnTimer.current = window.setTimeout(() => navigate("/queue"), 1500);
  }

  function undoReturn(): void {
    if (returnTimer.current) window.clearTimeout(returnTimer.current);
    returnTimer.current = null;
    setPendingReturn(false);
  }

  function handleOverride(submission: OverrideSubmission): void {
    submitReview.mutate(
      { action: "override", ...submission },
      { onSuccess: () => { setOverrideOpen(false); afterReview(); } },
    );
  }

  if (query.isLoading) {
    return (
      <div className="space-y-6" aria-busy="true" aria-label="Loading case">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-2">
            <Skeleton className="h-3 w-16" />
            <Skeleton className="h-7 w-56" />
            <Skeleton className="h-4 w-40" />
          </div>
          <Skeleton className="h-8 w-48" />
        </div>
        <Skeleton className="h-16 w-full" />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-20 w-full" />
          ))}
        </div>
        <Skeleton className="h-8 w-80" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (query.isError) {
    if (query.error.status === 404) {
      return (
        <EmptyState
          title="Case not found"
          description="This case does not exist, or it belongs to another tenant."
        />
      );
    }
    return (
      <ErrorState
        title="Could not load the case"
        message={query.error.message}
        correlationId={query.error.correlationId}
        onRetry={() => void query.refetch()}
      />
    );
  }

  if (!data) return null;

  const decision = data.decision;
  const consentRevoked = data.consent_status === "REVOKED";
  const fraudRouted = decision ? isFraudRouted(decision) : false;
  const writerAllowed = session?.role !== "AUDITOR";
  const roleAllowed = writerAllowed && (!fraudRouted || session?.role === "FRAUD_REVIEWER");
  const alreadyResolved = decision?.resolved ?? false;
  const disabled =
    !decision || alreadyResolved || consentRevoked || !roleAllowed || pendingReturn || !online;
  const disabledReason = !decision
    ? "There is no decision to act on."
    : alreadyResolved
      ? "This case has already been resolved."
      : consentRevoked
        ? "Consent has been revoked, so actions are disabled."
        : !writerAllowed
          ? "The auditor role is read-only; a credit analyst, fraud reviewer, or policy owner is required."
        : !roleAllowed
          ? "Only a fraud reviewer can act on a fraud-routed case."
          : !online
            ? "Reconnect before taking an action."
            : "";

  return (
    <FeatureDrawerContext.Provider value={{ open: openFeature }}>
      <div className="flex flex-col gap-4">
        {!online ? <OfflineBanner /> : null}
        {consentRevoked ? (
          <Banner tone="warn">
            Consent has been revoked. Actions are disabled; this decision remains readable as of
            when it was made.
          </Banner>
        ) : null}
        {data.stale.is_stale ? (
          <Banner tone="info">
            <span>{data.stale.new_event_count} new event(s) arrived after this decision. Re-decide to avoid mixing vintages.</span>{" "}
            <Button size="sm" variant="secondary" disabled={!online || !writerAllowed || redecide.isPending} onClick={() => redecide.mutate()}>{redecide.isPending ? "Re-deciding…" : "Re-decide now"}</Button>
          </Banner>
        ) : null}
        {pendingReturn ? (
          <div role="status" className="flex items-center gap-3 rounded border border-positive bg-surface px-3 py-2 text-sm">
            <span className="text-positive">Decision recorded. Returning to the queue…</span>
            <Button variant="ghost" size="sm" onClick={undoReturn}>
              Undo
            </Button>
          </div>
        ) : null}
        {submitReview.isError ? (
          <Banner tone="warn">
            {submitReview.error.message}
            {submitReview.error.status === 409
              ? " Refreshing to show the recorded outcome."
              : ""}
          </Banner>
        ) : null}

        <div className="sticky top-0 z-20 bg-sunken md:static">
          <CaseHeader
            data={data}
            actions={{
              onConfirm: () => setConfirmOpen(true),
              onOverride: () => setOverrideOpen(true),
              onRequestEvidence: () => setParam("tab", "recourse"),
              disabled,
              disabledReason,
              busy: submitReview.isPending,
            }}
          />
          <DecisionSummary data={data} />
        </div>

        <AssessmentSummary chips={data.chips} onSelectTab={(tab) => setParam("tab", tab)} />

        <p className="text-sm text-muted">
          <span className="font-medium text-ink">Bureau-only counterfactual:</span>{" "}
          {data.bureau_only.outcome.replace(/_/g, " ")} — {data.bureau_only.note}
        </p>
        <CaseTabs active={activeTab} onSelect={(tab) => setParam("tab", tab)} />

        <div>
          {activeTab === "evidence" ? (
            <EvidenceTab data={data} applicationId={applicationId} />
          ) : activeTab === "assessment" ? (
            <AssessmentTab data={data} />
          ) : activeTab === "verification" ? (
            <VerificationTab data={data} />
          ) : activeTab === "recourse" ? (
            decision ? (
              <RecourseTab data={data} decisionId={decision.id} onRerun={() => void query.refetch()} />
            ) : (
              <p className="text-sm text-muted">No decision, so there is no recourse to offer.</p>
            )
          ) : (
            <DecisionAuditTab data={data} onSelectTab={(tab) => setParam("tab", tab)} />
          )}
        </div>

        <EvidenceDrawer
          snapshotId={data.feature_snapshot_id}
          featureKey={feature}
          onClose={closeFeature}
        />

        <ConfirmRecommendationModal
          data={data}
          open={confirmOpen}
          onOpenChange={setConfirmOpen}
          submitting={submitReview.isPending}
          onConfirm={() =>
            submitReview.mutate(
              { action: "confirm" },
              {
                onSuccess: () => {
                  setConfirmOpen(false);
                  afterReview();
                },
              },
            )
          }
        />

        {decision ? (
          <OverrideModal
            decisionId={decision.id}
            recommendation={decision.outcome.replace(/_/g, " ")}
            open={overrideOpen}
            onOpenChange={setOverrideOpen}
            onSubmit={handleOverride}
            submitting={submitReview.isPending}
            errorMessage={submitReview.isError ? submitReview.error.message : undefined}
          />
        ) : null}
      </div>
    </FeatureDrawerContext.Provider>
  );
}
