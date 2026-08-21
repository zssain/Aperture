import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Route, Routes, useNavigate } from "react-router-dom";

import { renderWithProviders, ANALYST_SESSION } from "../../test/utils";
import { IngestPage } from "./IngestPage";
import { PipelineProgress } from "./PipelineProgress";
import type { PipelineJob } from "./useIngest";

const APP_ID = "00000000-0000-0000-0000-000000000101";
const APPLICANT_ID = "00000000-0000-0000-0000-000000000102";
const JOB_ID = "00000000-0000-0000-0000-000000000103";

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", "X-Correlation-ID": "test-cid" },
  });
}

function intake(overrides: Record<string, unknown> = {}) {
  return {
    status: "QUEUED",
    already_ingested: false,
    application_id: APP_ID,
    applicant_id: APPLICANT_ID,
    application_status: "PROCESSING",
    job_id: JOB_ID,
    ingestion: null,
    existing_case_url: null,
    ...overrides,
  };
}

const COMPLETE_JOB: PipelineJob = {
  id: JOB_ID,
  job_type: "INGEST",
  status: "SUCCEEDED",
  attempts: 1,
  max_attempts: 5,
  error: null,
  result: {
    application_id: APP_ID,
    decision_id: "00000000-0000-0000-0000-000000000104",
    outcome: "REVIEW_EVIDENCE",
    retryable_stage: null,
    stages: [
      { key: "consent", label: "Consent", status: "complete", count: 1 },
      { key: "fetching", label: "Fetching evidence", status: "complete", count: 42 },
      { key: "normalising", label: "Normalising", status: "complete", count: 42 },
      { key: "features", label: "Computing features", status: "complete", count: 28 },
      { key: "assessing", label: "Assessing", status: "complete", count: 4 },
      { key: "decided", label: "Decided", status: "complete", count: 1 },
    ],
  },
};

afterEach(() => {
  vi.unstubAllGlobals();
});

async function fillApplicant(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.type(screen.getByLabelText("Applicant name"), "Mira Shah");
  await user.type(screen.getByLabelText("External reference"), "EXT-101");
  await user.selectOptions(screen.getByLabelText("Occupation"), "GIG");
  await user.type(screen.getByLabelText("Declared monthly income (₹)"), "50000");
  await user.type(screen.getByLabelText("Requested amount (₹)"), "20000");
  const tenor = screen.getByLabelText("Requested tenor (months)");
  await user.clear(tenor);
  await user.type(tenor, "12");
}

function renderPage() {
  return renderWithProviders(
    <Routes>
      <Route path="/ingest" element={<IngestPage />} />
      <Route path="/cases/:id" element={<p>Case destination</p>} />
    </Routes>,
    { route: "/ingest", session: ANALYST_SESSION },
  );
}

function LeaveIngestButton() {
  const navigate = useNavigate();
  return <button onClick={() => navigate("/away")}>Leave ingest</button>;
}

describe("IngestPage", () => {
  it("discloses both evidence weights before selection and has no axe violations", async () => {
    const rendered = renderPage();
    expect(screen.getByText("Verified · recommended · highest evidence weight")).toBeVisible();
    expect(screen.getByText("Accepted at lower evidence weight")).toBeVisible();
    expect(screen.getAllByRole("radio")).toHaveLength(2);
    expect(await axe(rendered.container)).toHaveNoViolations();

    await userEvent.click(screen.getByLabelText(/Connect financial accounts/));
    expect(screen.getByRole("heading", { name: "Applicant authorisation" })).toBeVisible();
    expect(await axe(rendered.container)).toHaveNoViolations();

    await userEvent.click(screen.getByLabelText(/Upload statement/));
    expect(screen.getByLabelText("Statement file")).toHaveAttribute("type", "file");
    expect(await axe(rendered.container)).toHaveNoViolations();
  });

  it("connects with explicit unselected-by-default consent and lands in the case", async () => {
    const requests: Request[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        const request = new Request(
          path.startsWith("http") ? path : `https://testserver${path}`,
          init,
        );
        requests.push(request);
        if (request.url.endsWith(`/api/v1/jobs/${JOB_ID}`)) return response(COMPLETE_JOB);
        if (request.url.endsWith("/api/v1/applications")) return response(intake(), 201);
        throw new Error(`Unexpected request: ${request.url}`);
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await fillApplicant(user);
    await user.click(screen.getByLabelText(/Connect financial accounts/));
    expect(screen.getByLabelText("Bank accounts")).not.toBeChecked();
    expect(screen.getByLabelText(/explicitly grants this consent/)).not.toBeChecked();
    await user.click(screen.getByLabelText("Bank accounts"));
    await user.click(screen.getByLabelText(/explicitly grants this consent/));
    await user.click(screen.getByRole("button", { name: "Connect and start pipeline" }));

    expect(await screen.findByText("Case destination")).toBeVisible();
    const applicationRequest = requests.find((request) => request.url.endsWith("/applications"));
    expect(applicationRequest).toBeDefined();
    const payload = (await applicationRequest?.json()) as {
      consent_granted: boolean;
      scope: string[];
      requested_amount_paise: number;
    };
    expect(payload).toMatchObject({
      consent_granted: true,
      scope: ["BANK"],
      requested_amount_paise: 2_000_000,
    });
  });

  it("uploads successfully, polls through pending progress, and lands in the case", async () => {
    let jobPolls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/v1/applications/documents")) {
          return response(
            intake({
              ingestion: {
                status: "OK",
                snapshot_id: "snapshot-1",
                tier: "DECLARED_DOCUMENT",
                already_ingested: false,
                ingested: 7,
                deduplicated: 0,
                rejected: 0,
                rejected_reasons: [],
                provenance: [],
              },
            }),
            201,
          );
        }
        if (url.endsWith(`/api/v1/jobs/${JOB_ID}`)) {
          jobPolls += 1;
          if (jobPolls === 1) {
            return response({
              ...COMPLETE_JOB,
              status: "PENDING",
              result: {
                stages: COMPLETE_JOB.result?.stages?.map((stage, index) => ({
                  ...stage,
                  status: index < 3 ? "complete" : "pending",
                })),
              },
            });
          }
          return response(COMPLETE_JOB);
        }
        throw new Error(`Unexpected request: ${url}`);
      }),
    );

    const user = userEvent.setup();
    renderPage();
    await fillApplicant(user);
    await user.click(screen.getByLabelText(/Upload statement/));
    await user.upload(
      screen.getByLabelText("Statement file"),
      new File(["Date,Description,Amount\n2026-01-01,Income,100"], "clean_gig.csv", {
        type: "text/csv",
      }),
    );
    await user.click(screen.getByRole("button", { name: "Upload and start case" }));

    expect(await screen.findByText("Computing features: pending")).toBeVisible();
    expect(await screen.findByText("Case destination", {}, { timeout: 2_500 })).toBeVisible();
    expect(jobPolls).toBeGreaterThanOrEqual(2);
  });

  it("reports rejected rows and retains a malformed selected file for correction", async () => {
    let uploadCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/v1/applications/documents")) {
          uploadCount += 1;
          if (uploadCount === 1) {
            return response(
              {
                detail: {
                  code: "SCHEMA_ERROR",
                  message:
                    "Missing required columns. Expected columns: Date, Description, Amount.",
                },
              },
              422,
            );
          }
          return response(
            intake({
              ingestion: {
                status: "OK",
                snapshot_id: "snapshot-1",
                tier: "DECLARED_DOCUMENT",
                already_ingested: false,
                ingested: 7,
                deduplicated: 2,
                rejected: 1,
                rejected_reasons: [{ row: 9, reason: "unparseable date" }],
                provenance: [],
              },
            }),
            201,
          );
        }
        if (url.endsWith(`/api/v1/jobs/${JOB_ID}`)) {
          return response({ ...COMPLETE_JOB, status: "RUNNING", result: { stages: [] } });
        }
        throw new Error(`Unexpected request: ${url}`);
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await fillApplicant(user);
    await user.click(screen.getByLabelText(/Upload statement/));
    const input = screen.getByLabelText("Statement file") as HTMLInputElement;
    const malformed = new File(["Txn Date,Value\n2026-01-01,1"], "malformed_columns.csv", {
      type: "text/csv",
    });
    await user.upload(input, malformed);
    await user.click(screen.getByRole("button", { name: "Upload and start case" }));
    expect(await screen.findByText(/Expected columns: Date, Description, Amount/)).toBeVisible();
    expect(input.files?.item(0)?.name).toBe("malformed_columns.csv");

    await user.click(screen.getByRole("button", { name: "Upload and start case" }));
    expect(await screen.findByText("Ingested")).toBeVisible();
    expect(screen.getByText("Deduplicated")).toBeVisible();
    expect(screen.getByText("Rejected rows and reasons")).toBeVisible();
    expect(screen.getByText(/Row 9: unparseable date/)).toBeVisible();
  });

  it("creates an undecided awaiting-consent case when consent is declined", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        response(
          intake({
            status: "AWAITING_CONSENT",
            application_status: "AWAITING_CONSENT",
            job_id: null,
          }),
          201,
        ),
      ),
    );
    const user = userEvent.setup();
    renderPage();
    await fillApplicant(user);
    await user.click(screen.getByLabelText(/Connect financial accounts/));
    await user.click(screen.getByRole("button", { name: "Applicant declines consent" }));
    expect(await screen.findByText(/created in AWAITING_CONSENT/)).toBeVisible();
    expect(screen.getByText(/has not been decided/)).toBeVisible();
  });

  it("shows a provider-stage failure with a working retry while later stages complete", async () => {
    const onRetry = vi.fn();
    const partialJob: PipelineJob = {
      ...COMPLETE_JOB,
      result: {
        ...COMPLETE_JOB.result,
        retryable_stage: "fetching",
        sources: [
          { connection_id: "bank", source_type: "BANK", status: "UNAVAILABLE" },
          { connection_id: "upi", source_type: "UPI", status: "OK", ingested: 42 },
        ],
        stages: COMPLETE_JOB.result?.stages?.map((stage) =>
          stage.key === "fetching"
            ? { ...stage, status: "failed", message: "1 source unavailable; others completed." }
            : stage,
        ),
      },
    };
    const rendered = renderWithProviders(
      <PipelineProgress job={partialJob} onRetry={onRetry} />,
      { session: ANALYST_SESSION },
    );
    expect(screen.getByText("Fetching evidence: failed")).toBeVisible();
    expect(screen.getByText("Decided: complete")).toBeVisible();
    expect(screen.getByText(/BANK: UNAVAILABLE — retrying/)).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Retry fetching evidence" }));
    expect(onRetry).toHaveBeenCalledWith("fetching");
    expect(await axe(rendered.container)).toHaveNoViolations();
  });

  it("shows elapsed time while a pipeline stage is running", () => {
    const runningJob: PipelineJob = {
      ...COMPLETE_JOB,
      status: "RUNNING",
      result: {
        stages: [
          {
            key: "fetching",
            label: "Fetching evidence",
            status: "running",
            started_at: new Date(Date.now() - 5_000).toISOString(),
          },
        ],
      },
    };

    renderWithProviders(<PipelineProgress job={runningJob} onRetry={vi.fn()} />, {
      session: ANALYST_SESSION,
    });
    expect(screen.getByText("Fetching evidence: running")).toBeVisible();
    expect(screen.getByText(/^[45]s$/)).toBeVisible();
  });

  it("explains zero usable evidence and leaves the case undecided", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/v1/applications/documents")) {
          return response(
            intake({
              ingestion: {
                status: "OK",
                snapshot_id: "snapshot-empty",
                tier: "DECLARED_DOCUMENT",
                already_ingested: false,
                ingested: 0,
                deduplicated: 0,
                rejected: 2,
                rejected_reasons: [
                  { row: 2, reason: "unparseable date" },
                  { row: 3, reason: "invalid amount" },
                ],
                provenance: [],
              },
            }),
            201,
          );
        }
        if (url.endsWith(`/api/v1/jobs/${JOB_ID}`)) {
          return response({
            ...COMPLETE_JOB,
            result: {
              application_id: APP_ID,
              outcome: "ZERO_USABLE_EVIDENCE",
              retryable_stage: null,
              stages: [
                { key: "consent", label: "Consent", status: "complete", count: 1 },
                { key: "fetching", label: "Fetching evidence", status: "complete", count: 0 },
                {
                  key: "normalising",
                  label: "Normalising",
                  status: "failed",
                  count: 0,
                  message: "No usable evidence was found. The case was created but not decided.",
                },
                { key: "features", label: "Computing features", status: "pending" },
                { key: "assessing", label: "Assessing", status: "pending" },
                { key: "decided", label: "Decided", status: "pending" },
              ],
            },
          });
        }
        throw new Error(`Unexpected request: ${url}`);
      }),
    );

    const user = userEvent.setup();
    renderPage();
    await fillApplicant(user);
    await user.click(screen.getByLabelText(/Upload statement/));
    await user.upload(
      screen.getByLabelText("Statement file"),
      new File(["Date,Description,Amount\ninvalid,Bad,NaN"], "unusable.csv", {
        type: "text/csv",
      }),
    );
    await user.click(screen.getByRole("button", { name: "Upload and start case" }));

    expect(await screen.findByText(/case exists, but no decision was made/)).toBeVisible();
    expect(screen.getByText("Normalising: failed")).toBeVisible();
    expect(screen.queryByText("Case destination")).not.toBeInTheDocument();
  });

  it("does not send a cancellation request when the user navigates away mid-pipeline", async () => {
    const requests: Request[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const request = new Request(
          url.startsWith("http") ? url : `https://testserver${url}`,
          init,
        );
        requests.push(request);
        if (request.url.endsWith("/api/v1/applications")) return response(intake(), 201);
        if (request.url.endsWith(`/api/v1/jobs/${JOB_ID}`)) {
          return response({
            ...COMPLETE_JOB,
            status: "RUNNING",
            result: {
              stages: [
                { key: "consent", label: "Consent", status: "complete", count: 1 },
                {
                  key: "fetching",
                  label: "Fetching evidence",
                  status: "running",
                  started_at: new Date().toISOString(),
                },
              ],
            },
          });
        }
        throw new Error(`Unexpected request: ${request.url}`);
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(
      <Routes>
        <Route
          path="/ingest"
          element={
            <>
              <LeaveIngestButton />
              <IngestPage />
            </>
          }
        />
        <Route path="/away" element={<p>Away from ingest</p>} />
      </Routes>,
      { route: "/ingest", session: ANALYST_SESSION },
    );
    await fillApplicant(user);
    await user.click(screen.getByLabelText(/Connect financial accounts/));
    await user.click(screen.getByLabelText("Bank accounts"));
    await user.click(screen.getByLabelText(/explicitly grants this consent/));
    await user.click(screen.getByRole("button", { name: "Connect and start pipeline" }));
    expect(await screen.findByText("Fetching evidence: running")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Leave ingest" }));
    expect(await screen.findByText("Away from ingest")).toBeVisible();
    await waitFor(() => {
      expect(
        requests.some(
          (request) =>
            request.method === "DELETE" || /cancel/i.test(new URL(request.url).pathname),
        ),
      ).toBe(false);
    });
    expect(requests.some((request) => request.url.endsWith("/api/v1/applications"))).toBe(true);
  });

  it("shows duplicate upload as a link to the existing case", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        response(
          intake({
            status: "ALREADY_INGESTED",
            job_id: null,
            existing_case_url: `/cases/${APP_ID}`,
          }),
          201,
        ),
      ),
    );
    const user = userEvent.setup();
    renderPage();
    await fillApplicant(user);
    await user.click(screen.getByLabelText(/Upload statement/));
    await user.upload(
      screen.getByLabelText("Statement file"),
      new File(["Date,Description,Amount\n2026-01-01,Income,100"], "clean.csv", {
        type: "text/csv",
      }),
    );
    await user.click(screen.getByRole("button", { name: "Upload and start case" }));
    const link = await screen.findByRole("link", { name: "Open the existing case" });
    expect(link).toHaveAttribute("href", `/cases/${APP_ID}`);
  });

  it("uses inline product-bound validation and is keyboard reachable", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByLabelText(/Connect financial accounts/));
    await user.click(screen.getByRole("button", { name: "Applicant declines consent" }));
    expect(screen.getByText("Enter the applicant's name.")).toBeVisible();
    expect(screen.getByText(/₹1,000 to ₹50,00,000/)).toBeVisible();

    fireEvent.keyDown(screen.getByLabelText("Applicant name"), { key: "Tab" });
    expect(screen.getByLabelText("Applicant name")).toHaveAttribute("aria-invalid", "true");
  });
});
