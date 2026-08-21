import { expect, test } from "@playwright/test";

test("queue switches from table to cards below 768", async ({ page }) => {
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: { user_id: "1", email: "a@b.test", full_name: "Analyst", role: "CREDIT_ANALYST", tenant_id: "2", tenant_name: "Acme" } }));
  await page.route("**/api/v1/queue?*", (route) => route.fulfill({ json: { view: "my-exceptions", counts: { "my-exceptions": 1 }, rows: [{ id: "r", application_id: "a", applicant_name: "Responsive Applicant", applicant_ref: "R1", amount_paise: null, routed_because: { text: "Evidence needed", rule_number: 4 }, recommendation: { action: "REFER", band: null, approved_limit_paise: null, tenor_months: null, annual_rate_bps: null }, pd: { value: null, status: "unavailable" }, coverage: { value: 40, status: "measured" }, verification: "UNKNOWN", waiting_seconds: 1, decided_at: new Date().toISOString() }], next_cursor: null, auto_decided_24h: 0 } }));
  await page.setViewportSize({ width: 375, height: 800 }); await page.goto("/queue");
  await expect(page.getByRole("button", { name: /Responsive Applicant/ })).toBeVisible();
  await page.setViewportSize({ width: 768, height: 800 });
  await expect(page.getByRole("table", { name: "Cases awaiting review" })).toBeVisible();
  await page.setViewportSize({ width: 1024, height: 800 });
  await expect(page.getByRole("table", { name: "Cases awaiting review" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Amount" })).toBeHidden();
  await expect(page.getByRole("columnheader", { name: "Sources" })).toBeHidden();
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.getByRole("columnheader", { name: "Coverage" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Amount" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Sources" })).toBeVisible();
});

test("case file uses select, single column, then two-column tab bodies", async ({ page }) => {
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: { user_id: "1", email: "a@b.test", full_name: "Analyst", role: "CREDIT_ANALYST", tenant_id: "2", tenant_name: "Acme" } }));
  await page.route("**/api/v1/cases/case-responsive", (route) => route.fulfill({ json: {
    application: { id: "case-responsive", status: "REFERRED", product: null, requested_amount_paise: 100000, requested_tenor_months: 12, created_at: new Date().toISOString() },
    applicant: { id: "applicant", external_ref: "R1", display_name: "Responsive Applicant", phone: null }, case_age_seconds: 60, consent_status: "GRANTED", stale: { is_stale: false, new_event_count: 0 }, feature_snapshot_id: "snapshot", sources: [],
    decision: { id: "decision", action: "REFER", routing: "CREDIT", outcome: "REVIEW_EVIDENCE", policy_version: "1", approved_limit_paise: null, terms: {}, fired_rules: [{ number: 4, name: "coverage", outcome: "REVIEW_EVIDENCE" }], exploration_cohort: false, is_final: false, decided_at: new Date().toISOString(), reasons: [], resolved: false },
    assessments: {
      RISK: { kind: "RISK", engine_version: "1", model_version: "1", calibration_status: "UNCALIBRATED", payload: { pd: .2, contributions: [], reason_codes: [] } },
      COVERAGE: { kind: "COVERAGE", engine_version: "1", model_version: null, calibration_status: "NOT_APPLICABLE", payload: { score: 40, band: "LOW", weights_version: "1", components: [], missing_sources: [] } },
      AFFORDABILITY: { kind: "AFFORDABILITY", engine_version: "1", model_version: null, calibration_status: "NOT_APPLICABLE", payload: { status: "INDETERMINATE", income_basis: "unknown", net_monthly_income_paise: null, recurring_obligations_paise: 0, essential_expenses_paise: 0, disposable_income_paise: null, new_emi_paise: null, existing_emi_paise: 0, dsr: null, dsr_ceiling: .5, max_supportable_principal_paise: null } },
      MANIPULATION: { kind: "MANIPULATION", engine_version: "1", model_version: null, calibration_status: "NOT_APPLICABLE", payload: {} },
    }, assessment_failed: false, chips: { pd: { value: .2, status: "uncalibrated" }, coverage: { score: 40, band: "LOW", status: "measured" }, affordability: { status: "INDETERMINATE", headroom_paise: null }, verification: "UNKNOWN" }, manipulation_findings: [], recourse: [], reviews: [], blocking_tab: "assessment", bureau_only: { available: false, outcome: "UNAVAILABLE", action: null, note: "No bureau file." },
  } }));
  await page.setViewportSize({ width: 375, height: 800 }); await page.goto("/cases/case-responsive");
  await expect(page.getByRole("combobox", { name: "Case section" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Decision" }).locator("..")).toHaveCSS("position", "sticky");
  await page.setViewportSize({ width: 768, height: 800 });
  await expect(page.getByRole("tablist", { name: "Case sections" })).toBeVisible();
  await expect(page.getByTestId("case-tab-body")).toHaveCSS("display", "block");
  await page.setViewportSize({ width: 1024, height: 800 });
  await expect(page.getByTestId("case-tab-body")).toHaveCSS("display", "block");
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.getByTestId("case-tab-body")).toHaveCSS("display", "grid");
  await expect(page.getByTestId("case-tab-body")).toHaveCSS("grid-template-columns", /.+ .+/);
});
