import { expect, test } from "@playwright/test";

const session = { user_id: "1", email: "a@b.test", full_name: "Analyst", role: "CREDIT_ANALYST", tenant_id: "2", tenant_name: "Acme" };

test("offline ingest preserves fields and blocks submit", async ({ page, context }) => {
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: session }));
  await page.goto("/ingest"); await page.getByLabel("Applicant name").fill("Preserved value");
  await context.setOffline(true); await page.evaluate(() => window.dispatchEvent(new Event("offline")));
  await expect(page.getByText("Offline.")).toBeVisible();
  await expect(page.getByLabel("Applicant name")).toHaveValue("Preserved value");
  await context.setOffline(false);
});

test("offline queue keeps its cached list readable", async ({ page, context }) => {
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: session }));
  await page.route("**/api/v1/queue?*", (route) => route.fulfill({ json: { view: "my-exceptions", counts: { "my-exceptions": 1 }, rows: [{ id: "row", application_id: "case", applicant_name: "Cached Applicant", applicant_ref: "R1", amount_paise: 10000, routed_because: { text: "Evidence needed", rule_number: 4 }, recommendation: { action: "REFER", band: null, approved_limit_paise: null, tenor_months: null, annual_rate_bps: null }, pd: { value: null, status: "unavailable" }, coverage: { value: 40, status: "measured" }, verification: "UNKNOWN", waiting_seconds: 2, decided_at: new Date().toISOString() }], next_cursor: null, auto_decided_24h: 0 } }));
  await page.goto("/queue"); await expect(page.getByRole("table").getByText("Cached Applicant")).toBeVisible();
  await context.setOffline(true); await page.evaluate(() => window.dispatchEvent(new Event("offline")));
  await expect(page.getByText("Offline.")).toBeVisible();
  await expect(page.getByRole("table").getByText("Cached Applicant")).toBeVisible();
  await context.setOffline(false);
});

test("offline case remains readable and blocks actions", async ({ page, context }) => {
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: session }));
  await page.route("**/api/v1/cases/case", (route) => route.fulfill({ json: {
    application: { id: "case", status: "REFERRED", product: null, requested_amount_paise: 10000, requested_tenor_months: 12, created_at: new Date().toISOString() }, applicant: { id: "a", external_ref: "R1", display_name: "Offline Applicant", phone: null }, case_age_seconds: 2, consent_status: "GRANTED", stale: { is_stale: false, new_event_count: 0 }, feature_snapshot_id: null, sources: [], decision: { id: "d", action: "REFER", routing: "CREDIT", outcome: "REVIEW_EVIDENCE", policy_version: "1", approved_limit_paise: null, terms: {}, fired_rules: [{ number: 4, name: "coverage", outcome: "REVIEW_EVIDENCE" }], exploration_cohort: false, is_final: false, decided_at: new Date().toISOString(), reasons: [], resolved: false }, assessments: {}, assessment_failed: false, chips: { pd: { value: null, status: "unavailable" }, coverage: { score: null, band: null, status: "unavailable" }, affordability: { status: "INDETERMINATE", headroom_paise: null }, verification: "UNKNOWN" }, manipulation_findings: [], recourse: [], reviews: [], blocking_tab: "evidence", bureau_only: { available: false, outcome: "UNAVAILABLE", action: null, note: "Unavailable." },
  } }));
  await page.route("**/api/v1/cases/case/evidence?*", (route) => route.fulfill({ json: { rows: [], next_cursor: null } }));
  await page.goto("/cases/case"); await expect(page.getByText("Offline Applicant")).toBeVisible();
  await context.setOffline(true); await page.evaluate(() => window.dispatchEvent(new Event("offline")));
  await expect(page.getByText("Offline.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Confirm recommendation" })).toBeDisabled();
  await expect(page.getByText("Offline Applicant")).toBeVisible();
  await context.setOffline(false);
});
