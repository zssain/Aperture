import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "../../components/ui/Button";
import { ErrorState } from "../../components/ui/ErrorState";
import { OfflineBanner } from "../../components/ui/OfflineBanner";
import { PageHeader } from "../../components/ui/PageHeader";
import { useOnlineStatus } from "../../hooks/useOnlineStatus";
import { ApplicantForm, type ApplicantErrors } from "./ApplicantForm";
import { BankConsentModal, type AaConsentResult } from "./BankConsentModal";
import { BankPicker, DEMO_BANKS } from "./BankPicker";
import { ConsentStep } from "./ConsentStep";
import { DocumentUpload } from "./DocumentUpload";
import { ImportSummary } from "./ImportSummary";
import { PipelineProgress } from "./PipelineProgress";
import { SourceConnect, type EvidencePath } from "./SourceConnect";
import {
  useCreateConnectCase,
  useCreateDocumentCase,
  usePipelineJob,
  useRetryPipeline,
  type ApplicantValues,
  type CaseIntake,
  type SourceType,
} from "./useIngest";

const EMPTY_APPLICANT: ApplicantValues = {
  displayName: "",
  externalRef: "",
  declaredIncomeRupees: "",
  occupation: "",
  requestedAmountRupees: "",
  requestedTenorMonths: "12",
};

function futureDate(days: number): string {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function integerInRange(value: string, min: number, max: number): boolean {
  return /^\d+$/.test(value) && Number(value) >= min && Number(value) <= max;
}

function validateApplicant(values: ApplicantValues): ApplicantErrors {
  const errors: ApplicantErrors = {};
  if (!values.displayName.trim()) errors.displayName = "Enter the applicant's name.";
  if (!values.externalRef.trim()) errors.externalRef = "Enter an external reference.";
  if (!values.occupation) errors.occupation = "Select an occupation.";
  if (!integerInRange(values.declaredIncomeRupees, 1, 10_000_000)) {
    errors.declaredIncomeRupees = "Enter whole rupees from ₹1 to ₹1,00,00,000.";
  }
  if (!integerInRange(values.requestedAmountRupees, 1_000, 5_000_000)) {
    errors.requestedAmountRupees = "Enter whole rupees from ₹1,000 to ₹50,00,000.";
  }
  if (!integerInRange(values.requestedTenorMonths, 3, 60)) {
    errors.requestedTenorMonths = "Enter a tenor from 3 to 60 months.";
  }
  return errors;
}

export function IngestPage() {
  const online = useOnlineStatus();
  const navigate = useNavigate();
  const [applicant, setApplicant] = useState(EMPTY_APPLICANT);
  const [errors, setErrors] = useState<ApplicantErrors>({});
  const [path, setPath] = useState<EvidencePath | null>(null);
  const [bankId, setBankId] = useState<string | null>(null);
  const [authOpen, setAuthOpen] = useState(false);
  const [signInNotice, setSignInNotice] = useState<string | undefined>();
  const [consentGranted, setConsentGranted] = useState(false);
  const [scopes, setScopes] = useState<SourceType[]>([]);
  const [purpose, setPurpose] = useState("Credit underwriting");
  const [expiresOn, setExpiresOn] = useState(() => futureDate(90));
  const [consentError, setConsentError] = useState<string | undefined>();
  const [file, setFile] = useState<File | null>(null);
  const [intake, setIntake] = useState<CaseIntake | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);

  const connect = useCreateConnectCase();
  const upload = useCreateDocumentCase();
  const job = usePipelineJob(jobId);
  const retry = useRetryPipeline();
  const busy = connect.isPending || upload.isPending || jobId !== null;
  const mutationError = connect.error ?? upload.error;
  const uploadError = path === "upload" ? mutationError?.message : null;

  const completedApplicationId = job.data?.result?.application_id;
  const shouldAutoOpen =
    job.data?.status === "SUCCEEDED" &&
    Boolean(job.data.result?.decision_id) &&
    !job.data.result?.retryable_stage;

  // Let the import summary land before moving on — the numbers are the story.
  useEffect(() => {
    if (!shouldAutoOpen || !completedApplicationId) return;
    const timer = window.setTimeout(
      () => navigate(`/cases/${completedApplicationId}`),
      2_400,
    );
    return () => window.clearTimeout(timer);
  }, [completedApplicationId, navigate, shouldAutoOpen]);

  const selectedBank = DEMO_BANKS.find((bank) => bank.id === bankId) ?? null;
  const importTotals = useMemo(() => {
    if (intake?.ingestion) {
      return {
        ingested: intake.ingestion.ingested,
        deduplicated: intake.ingestion.deduplicated,
      };
    }
    const sources = job.data?.result?.sources ?? [];
    if (sources.length === 0) return null;
    return {
      ingested: sources.reduce((sum, source) => sum + (source.ingested ?? 0), 0),
      deduplicated: sources.reduce((sum, source) => sum + (source.deduplicated ?? 0), 0),
    };
  }, [intake, job.data?.result?.sources]);
  const showImportSummary = shouldAutoOpen && importTotals !== null && importTotals.ingested > 0;

  const notice = useMemo(() => {
    if (intake?.status === "AWAITING_CONSENT") {
      return "Case created in AWAITING_CONSENT. It has not been decided and is visible in Evidence needed.";
    }
    if (job.data?.result?.outcome === "ZERO_USABLE_EVIDENCE") {
      return "No usable evidence was found. The case exists, but no decision was made.";
    }
    return null;
  }, [intake, job.data]);

  function updateApplicant(field: keyof ApplicantValues, value: string): void {
    setApplicant((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: undefined }));
  }

  function validApplicant(): boolean {
    const next = validateApplicant(applicant);
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  function openBankSignIn(): void {
    // Launch the Account Aggregator sign-in popup, but only once the applicant details are
    // complete (we need them to create the case). If they are missing, say so right here
    // instead of failing silently — the form errors themselves are above the fold.
    if (!validApplicant()) {
      setSignInNotice("Add the applicant's details at the top of the page before signing in to a bank.");
      return;
    }
    setSignInNotice(undefined);
    setAuthOpen(true);
  }

  function handlePickBank(id: string): void {
    setBankId(id);
    connect.reset();
    openBankSignIn();
  }

  function handleAaApprove(result: AaConsentResult): void {
    // Consent was approved inside the AA popup; mirror it into the recorded artefact and start
    // the pipeline with exactly the scopes the applicant ticked.
    setConsentGranted(true);
    setScopes(result.scopes);
    setPurpose(result.purpose);
    setExpiresOn(result.expiresOn);
    setConsentError(undefined);
    setAuthOpen(false);
    connect.mutate(
      {
        applicant,
        consentGranted: true,
        purpose: result.purpose,
        scopes: result.scopes,
        expiresAt: new Date(`${result.expiresOn}T23:59:59Z`).toISOString(),
      },
      {
        onSuccess: (created) => {
          setIntake(created);
          setJobId(created.job_id);
        },
      },
    );
  }

  function submitConnect(granted: boolean): void {
    if (!validApplicant()) return;
    if (granted && bankId === null) {
      setConsentError("Select the applicant's bank before requesting consent.");
      return;
    }
    if (granted && (!consentGranted || scopes.length === 0 || !purpose.trim() || !expiresOn)) {
      setConsentError("Explicit consent, at least one scope, purpose, and validity are required.");
      return;
    }
    setConsentError(undefined);
    connect.mutate(
      {
        applicant,
        consentGranted: granted,
        purpose,
        scopes: granted ? scopes : [],
        expiresAt: granted ? new Date(`${expiresOn}T23:59:59Z`).toISOString() : null,
      },
      {
        onSuccess: (result) => {
          setIntake(result);
          setJobId(result.job_id);
        },
      },
    );
  }

  function submitUpload(): void {
    if (!validApplicant() || file === null) return;
    upload.mutate(
      { applicant, file },
      {
        onSuccess: (result) => {
          setIntake(result);
          setJobId(result.job_id);
        },
      },
    );
  }

  function retryStage(stage: string): void {
    if (!job.data) return;
    retry.mutate(
      { jobId: job.data.id, stage },
      {
        onSuccess: (retried) => setJobId(retried.id),
      },
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      {!online ? <OfflineBanner detail="Your form is preserved locally. Reconnect before starting ingestion." /> : null}
      <PageHeader
        eyebrow="Case management"
        title="New case"
        description="Create the request, collect evidence with explicit consent, and follow every pipeline stage through to a decision."
      />

      <ApplicantForm values={applicant} errors={errors} disabled={busy} onChange={updateApplicant} />
      <SourceConnect
        path={path}
        disabled={busy}
        onChange={(next) => {
          setPath(next);
          connect.reset();
          upload.reset();
        }}
      />

      {path === "connect" ? (
        <>
          <BankPicker selected={bankId} disabled={busy} onChange={handlePickBank} />
          {selectedBank ? (
            <div className="rounded border border-border bg-surface p-4">
              <div className="flex flex-wrap items-center gap-3">
                <p className="text-sm text-muted">
                  {consentGranted
                    ? `Consent captured from ${selectedBank.name} via the Account Aggregator.`
                    : `The applicant authorises sharing at ${selectedBank.name} — Aperture never sees their credentials.`}
                </p>
                <Button
                  variant={consentGranted ? "secondary" : "primary"}
                  className="ml-auto"
                  disabled={busy || !online}
                  onClick={openBankSignIn}
                >
                  {consentGranted ? "Review consent" : `Sign in at ${selectedBank.name}`}
                </Button>
              </div>
              {signInNotice ? (
                <p role="status" className="mt-2 text-sm text-negative">
                  {signInNotice}
                </p>
              ) : null}
            </div>
          ) : null}
          <BankConsentModal
            open={authOpen}
            bank={selectedBank}
            applicantName={applicant.displayName}
            purpose={purpose}
            expiresOn={expiresOn}
            busy={connect.isPending}
            onOpenChange={setAuthOpen}
            onApprove={handleAaApprove}
          />
          <ConsentStep
            granted={consentGranted}
            scopes={scopes}
            purpose={purpose}
            expiresOn={expiresOn}
            bankName={selectedBank?.name ?? null}
            disabled={busy}
            error={consentError}
            onGrantedChange={(granted) => {
              setConsentGranted(granted);
              setConsentError(undefined);
            }}
            onScopeChange={(scope, checked) =>
              setScopes((current) =>
                checked ? [...current, scope] : current.filter((value) => value !== scope),
              )
            }
            onPurposeChange={setPurpose}
            onExpiresOnChange={setExpiresOn}
          />
          <div className="flex flex-wrap gap-3 rounded border border-border bg-surface p-4">
            <Button disabled={busy || !online} onClick={() => submitConnect(true)}>
              {connect.isPending ? "Creating case…" : "Connect and start pipeline"}
            </Button>
            <Button variant="secondary" disabled={busy || !online} onClick={() => submitConnect(false)}>
              Applicant declines consent
            </Button>
          </div>
        </>
      ) : null}

      {path === "upload" ? (
        <DocumentUpload
          file={file}
          ingestion={intake?.ingestion ?? null}
          disabled={busy || !online}
          error={uploadError}
          existingCaseUrl={intake?.existing_case_url}
          onFileChange={(next) => {
            setFile(next);
            upload.reset();
          }}
          onSubmit={submitUpload}
        />
      ) : null}

      {path === null ? (
        <p role="status" className="rounded border border-border bg-surface p-4 text-sm text-muted">
          Complete the applicant details, then choose either evidence path above.
        </p>
      ) : null}

      {mutationError && path !== "upload" ? (
        <ErrorState
          title="Could not start the case"
          message={mutationError.message}
          correlationId={mutationError.correlationId}
          onRetry={() => submitConnect(consentGranted)}
        />
      ) : null}
      {job.isError ? (
        <ErrorState
          title="Could not load pipeline progress"
          message={job.error.message}
          correlationId={job.error.correlationId}
          onRetry={() => void job.refetch()}
        />
      ) : null}
      {showImportSummary && importTotals ? (
        <ImportSummary
          ingested={importTotals.ingested}
          deduplicated={importTotals.deduplicated}
          sourceLabel={
            path === "connect"
              ? `${selectedBank?.name ?? "Bank"} · Account Aggregator sandbox`
              : `Uploaded statement${file ? ` · ${file.name}` : ""}`
          }
          tierLabel={path === "connect" ? "AA-verified" : "Declared document"}
          decisionReady
          onOpenCase={() => {
            if (completedApplicationId) navigate(`/cases/${completedApplicationId}`);
          }}
        />
      ) : null}
      {job.data ? (
        <PipelineProgress job={job.data} retrying={retry.isPending} onRetry={retryStage} />
      ) : null}

      {notice ? (
        <div role="status" className="rounded border border-caution bg-surface p-4 text-sm text-ink">
          <p>{notice}</p>
          {intake?.application_id ? (
            <Button
              className="mt-3"
              size="sm"
              variant="secondary"
              onClick={() => navigate(`/cases/${intake.application_id}`)}
            >
              Open case
            </Button>
          ) : null}
        </div>
      ) : null}
      {job.data?.result?.decision_id && job.data.result.retryable_stage ? (
        <Button variant="secondary" onClick={() => navigate(`/cases/${job.data?.result?.application_id}`)}>
          Continue to case without retrying unavailable source
        </Button>
      ) : null}
    </div>
  );
}
