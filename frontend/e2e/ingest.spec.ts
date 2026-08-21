import { expect, test } from "@playwright/test";

const applicationId = "00000000-0000-0000-0000-000000000201";
const jobId = "00000000-0000-0000-0000-000000000202";

test("connect intake is keyboard-completable and lands in the case", async ({ page }) => {
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({
      json: {
        user_id: "00000000-0000-0000-0000-000000000001",
        email: "analyst@example.com",
        full_name: "Ana Analyst",
        role: "CREDIT_ANALYST",
        tenant_id: "00000000-0000-0000-0000-0000000000aa",
        tenant_name: "Acme Credit",
      },
    }),
  );
  await page.route("**/api/v1/applications", (route) =>
    route.fulfill({
      status: 201,
      json: {
        status: "QUEUED",
        already_ingested: false,
        application_id: applicationId,
        applicant_id: "00000000-0000-0000-0000-000000000203",
        application_status: "PROCESSING",
        job_id: jobId,
        ingestion: null,
        existing_case_url: null,
      },
    }),
  );
  await page.route(`**/api/v1/jobs/${jobId}`, (route) =>
    route.fulfill({
      json: {
        id: jobId,
        job_type: "INGEST",
        status: "SUCCEEDED",
        attempts: 1,
        max_attempts: 5,
        error: null,
        result: {
          application_id: applicationId,
          decision_id: "00000000-0000-0000-0000-000000000204",
          outcome: "REVIEW_EVIDENCE",
          retryable_stage: null,
          stages: [
            { key: "consent", label: "Consent", status: "complete", count: 1 },
            { key: "fetching", label: "Fetching evidence", status: "complete", count: 45 },
            { key: "normalising", label: "Normalising", status: "complete", count: 45 },
            { key: "features", label: "Computing features", status: "complete", count: 28 },
            { key: "assessing", label: "Assessing", status: "complete", count: 4 },
            { key: "decided", label: "Decided", status: "complete", count: 1 },
          ],
        },
      },
    }),
  );
  await page.route(`**/api/v1/cases/${applicationId}`, (route) => route.abort());

  await page.goto("/ingest");
  await expect(page.getByText("Verified · recommended · highest evidence weight")).toBeVisible();
  await expect(page.getByText("Accepted at lower evidence weight")).toBeVisible();

  await page.getByLabel("Applicant name").focus();
  await page.keyboard.type("Mira Shah");
  await page.getByLabel("External reference").focus();
  await page.keyboard.type("EXT-E2E-1");
  await page.getByLabel("Occupation").focus();
  await page.keyboard.press("g");
  await page.getByLabel("Declared monthly income (₹)").focus();
  await page.keyboard.type("50000");
  await page.getByLabel("Requested amount (₹)").focus();
  await page.keyboard.type("20000");
  await page.getByLabel("Requested tenor (months)").focus();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.type("12");
  await page.getByLabel(/Connect financial accounts/).focus();
  await page.keyboard.press("Space");

  await expect(page.getByLabel("Bank accounts")).not.toBeChecked();
  await expect(page.getByLabel(/explicitly grants this consent/)).not.toBeChecked();
  await page.getByLabel("Bank accounts").focus();
  await page.keyboard.press("Space");
  await page.getByLabel(/explicitly grants this consent/).focus();
  await page.keyboard.press("Space");
  await page.getByRole("button", { name: "Connect and start pipeline" }).focus();
  await page.keyboard.press("Enter");

  await expect(page).toHaveURL(`/cases/${applicationId}`);
});
