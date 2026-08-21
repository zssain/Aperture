import { expect, test } from "@playwright/test";

const draftId = "00000000-0000-0000-0000-000000000016";
const liveId = "00000000-0000-0000-0000-000000000015";
const jobId = "00000000-0000-0000-0000-000000000160";
const baseRules = { policy_version: "policy-v2", min_coverage: 40, pd_decline_threshold: .25, pd_enhanced: .08, pd_standard: .15, cov_high: 75, cov_mid: 55, mandatory_review_ceiling_paise: 20000000, exploration_margin: .03, exploration_budget: .05, terms: { APPROVE_STARTER: { max_principal_paise: 5000000, max_tenor_months: 12, rate_band: "C", annual_rate_bps: 2200 } } };

test("policy owner edits, simulates, and publishes the exact draft", async ({ page }) => {
  let rules = structuredClone(baseRules); let hash = "draft-hash-1";
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: { user_id: liveId, email: "owner@example.com", full_name: "Policy Owner", role: "CREDIT_POLICY_OWNER", tenant_id: liveId, tenant_name: "Acme" } }));
  await page.route("**/api/v1/policies", async (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: [
      { id: draftId, version: 2, status: "DRAFT", rules, author: "Policy Owner", change_note: null, published_at: null, draft_hash: hash, validation: { ok: true, errors: [] } },
      { id: liveId, version: 1, status: "LIVE", rules: { ...baseRules, policy_version: "policy-v1" }, author: "Policy Owner", change_note: "Initial approved lending policy", published_at: new Date().toISOString(), draft_hash: "live", validation: { ok: true, errors: [] } },
    ] });
    return route.fulfill({ status: 201, json: {} });
  });
  await page.route(`**/api/v1/policies/${draftId}`, async (route) => {
    rules = (await route.request().postDataJSON()).rules; hash = "draft-hash-2";
    return route.fulfill({ json: { id: draftId, version: 2, status: "DRAFT", rules, draft_hash: hash, validation: { ok: true, errors: [] } } });
  });
  await page.route(`**/api/v1/policies/${draftId}/simulate`, (route) => route.fulfill({ status: 202, json: { job_id: jobId } }));
  await page.route(`**/api/v1/policies/${draftId}/simulation/${jobId}`, (route) => route.fulfill({ json: { job_id: jobId, status: "SUCCEEDED", draft_hash: hash, n_snapshots: 1000, approval_delta: .01, cohort_deltas: {}, transition_matrix: {}, modelled_bad_rate_delta: -.01, expected_loss_delta: -.02, caveats: ["Loss estimates inherit the cash-flow scorecard's UNCALIBRATED status and are directional only."], largest_flips: [] } }));
  await page.route(`**/api/v1/policies/${draftId}/publish`, (route) => route.fulfill({ json: { policy: { id: draftId, status: "LIVE" }, bulk_job_id: null } }));

  await page.setViewportSize({ width: 1440, height: 900 }); await page.goto("/policy");
  await page.getByLabel("Minimum coverage").fill("41");
  await expect(page.getByRole("button", { name: "Publish" })).toBeDisabled();
  await page.getByRole("button", { name: "Save draft" }).click();
  await page.getByRole("button", { name: "Simulate" }).click();
  await expect(page.getByText(/UNCALIBRATED/)).toBeVisible();
  await page.getByRole("button", { name: "Publish" }).click();
  await page.getByLabel(/Change note/).fill("Raise minimum coverage after book simulation.");
  await page.getByRole("dialog").getByRole("button", { name: "Publish" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
});

test("Policy Studio explicitly refuses mobile editing", async ({ page }) => {
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: { user_id: liveId, email: "owner@example.com", full_name: "Policy Owner", role: "CREDIT_POLICY_OWNER", tenant_id: liveId, tenant_name: "Acme" } }));
  await page.route("**/api/v1/policies", (route) => route.fulfill({ json: [] }));
  await page.setViewportSize({ width: 375, height: 800 }); await page.goto("/policy");
  await expect(page.getByText("Desktop required")).toBeVisible();
});
