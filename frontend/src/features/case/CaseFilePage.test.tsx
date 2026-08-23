import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ANALYST_SESSION, renderWithProviders } from "../../test/utils";
import { CaseFilePage } from "./CaseFilePage";
import type { CaseData } from "./useCase";

function makeCase(over: Partial<CaseData> = {}): CaseData {
  return {
    application: {
      id: "app-1", status: "OPEN", product: null,
      requested_amount_paise: 1_800_000, requested_tenor_months: 9,
      created_at: "2026-08-20T00:00:00Z",
    },
    applicant: { id: "a1", external_ref: "EXT-1", display_name: "Asha Kumar", phone: null },
    case_age_seconds: 7200,
    consent_status: "GRANTED",
    stale: { is_stale: false, new_event_count: 0 },
    feature_snapshot_id: "snap-1",
    sources: [
      {
        id: "s1", source_type: "BANK", tier: "AA_VERIFIED", status: "CONNECTED", provider: "AA",
        period_start: "2026-01-01T00:00:00Z", period_end: "2026-07-01T00:00:00Z",
        last_sync_at: "2026-08-01T00:00:00Z", freshness_days: 20,
      },
    ],
    decision: {
      id: "d1", action: "APPROVE_STARTER", routing: "AUTOMATED", outcome: "APPROVE_STARTER",
      policy_version: "1", resolved: false,
      approved_limit_paise: 1_800_000,
      terms: {
        approved_principal_paise: 1_800_000, approved_tenor_months: 9, annual_rate_bps: 2600,
        band: "C", graduation: { review_months: 4 },
      },
      fired_rules: [{ number: 9, name: "approve_starter", outcome: "APPROVE_STARTER" }],
      exploration_cohort: false, is_final: true, decided_at: "2026-08-20T00:00:00Z",
      reasons: [
        { code: "GATE_APPROVE_STARTER", message: "Approved", polarity: "POSITIVE", template_params: {}, order: 0 },
      ],
    },
    assessments: {
      RISK: {
        kind: "RISK", engine_version: "scorecard-v1", model_version: "scorecard-v1",
        calibration_status: "UNCALIBRATED",
        payload: {
          pd: 0.091, calibration_status: "UNCALIBRATED", model_version: "scorecard-v1",
          contributions: [
            { feature: "monthly_inflow_cv", value: 0.3, contribution: 0.12, direction: "increases_risk", present: true },
          ],
          reason_codes: [],
        },
      },
      COVERAGE: {
        kind: "COVERAGE", engine_version: "coverage-v1", model_version: null,
        calibration_status: "NOT_APPLICABLE",
        payload: {
          score: 41, band: "LOW", weights_version: "cov-v1",
          components: [{ name: "tier", weight: 40, fraction: 0.5, contribution: 20, detail: "AA" }],
          missing_sources: [{ source_type: "UTILITY", why: "not connected", coverage_delta: 8 }],
        },
      },
      AFFORDABILITY: {
        kind: "AFFORDABILITY", engine_version: "afford-v1", model_version: null,
        calibration_status: "NOT_APPLICABLE",
        payload: {
          status: "PASS", income_basis: "median", net_monthly_income_paise: 3_140_000,
          recurring_obligations_paise: 920_000, essential_expenses_paise: 1_730_000,
          disposable_income_paise: 490_000, new_emi_paise: 215_000, existing_emi_paise: 0,
          dsr: 0.36, dsr_ceiling: 0.5, max_supportable_principal_paise: 5_000_000,
        },
      },
      MANIPULATION: {
        kind: "MANIPULATION", engine_version: "manip-v1", model_version: null,
        calibration_status: "NOT_APPLICABLE",
        payload: { band: "CLEAR", findings: [], trigger_counts: {} },
      },
    },
    assessment_failed: false,
    chips: {
      pd: { value: 0.091, status: "uncalibrated" },
      coverage: { score: 41, band: "LOW", status: "measured" },
      affordability: { status: "PASS", headroom_paise: 490_000 },
      verification: "CLEAR",
    },
    manipulation_findings: [],
    recourse: [],
    reviews: [],
    blocking_tab: "assessment",
    bureau: {
      present: false,
      score: { value: null, status: "unavailable" },
      active_loans: { value: null, status: "unavailable" },
      delinquencies_12m: { value: null, status: "unavailable" },
    },
    bureau_only: {
      available: false, outcome: "REVIEW_EVIDENCE", action: "REFER",
      note: "A bureau-only lender lacks the cash-flow evidence.",
    },
    ...over,
  };
}

const EVIDENCE = {
  rows: [
    {
      id: "e1", occurred_at: "2026-07-01T00:00:00Z", direction: "CREDIT", amount_paise: 5_000_000,
      balance_paise: 2_000_000, description: "salary credit", category: "SALARY", confidence: 0.9,
    },
  ],
  next_cursor: null,
};

const CASHFLOW = [
  { month: "2026-06", inflow_paise: 5_000_000, outflow_paise: 3_500_000 },
  { month: "2026-07", inflow_paise: 5_100_000, outflow_paise: 3_400_000 },
];

const LINEAGE = {
  feature_key: "monthly_inflow_cv", version: "1", dtype: "float", window: "6m",
  formula_doc: "population CV of monthly income", null_policy: "mean_below_floor",
  monotonic_direction: "lower_better", value: 0.3, null_reason: null,
  contributing_event_ids: ["e1", "e2"], recomputed_value: 0.3, matches: true,
};

function json(body: unknown, statusCode = 200): Response {
  return new Response(JSON.stringify(body), {
    status: statusCode,
    headers: { "content-type": "application/json", "X-Correlation-ID": "cid-test" },
  });
}

function mockFetch(caseData: CaseData | null, caseStatus = 200): void {
  const fetchMock = vi.fn(async (url: string | URL) => {
    const u = String(url);
    if (u.includes("/lineage")) return json(LINEAGE);
    if (u.includes("/cashflow")) return json(CASHFLOW);
    if (u.includes("/evidence")) return json(EVIDENCE);
    if (caseStatus !== 200) return json({ detail: { code: "CASE_NOT_FOUND", message: "nope" } }, caseStatus);
    return json(caseData);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function renderCase(route: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/cases/:id" element={<CaseFilePage />} />
    </Routes>,
    { route, session: ANALYST_SESSION },
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("CaseFilePage", () => {
  it("renders the case and opens on blocking_tab (not the first tab)", async () => {
    mockFetch(makeCase());
    renderCase("/cases/app-1");

    // Decision summary: a readable headline plus the exact enum in a mono chip.
    expect(await screen.findByText("Approve · starter band")).toBeInTheDocument();
    expect(screen.getByText("APPROVE_STARTER")).toBeInTheDocument();
    // blocking_tab is "assessment": that tab is selected, Evidence (the first tab) is not.
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: "Assessment" })).toHaveAttribute("aria-selected", "true"),
    );
    expect(screen.getByRole("tab", { name: "Evidence" })).toHaveAttribute("aria-selected", "false");
    // The bureau-only counterfactual is displayed.
    expect(screen.getByText(/Bureau-only counterfactual:/)).toBeInTheDocument();
  });

  it("renders an uncalibrated PD as neutral with UNCAL (band chip and assessment tab)", async () => {
    mockFetch(makeCase());
    const { container } = renderCase("/cases/app-1");
    await screen.findByText("APPROVE_STARTER");
    // One UNCAL in the chip, one in the assessment tab PD.
    expect(screen.getAllByText("UNCAL").length).toBeGreaterThanOrEqual(2);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("opens the drawer on a number click and restores focus on close", async () => {
    mockFetch(makeCase());
    renderCase("/cases/app-1");
    await screen.findByText("APPROVE_STARTER");

    const trigger = screen.getByRole("button", { name: /monthly inflow variability/i });
    await userEvent.click(trigger);

    // Drawer shows the feature's formula (from the lineage endpoint).
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("population CV of monthly income")).toBeInTheDocument();

    await userEvent.click(within(dialog).getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    // Focus is restored to the number that opened it (Radix restores on close).
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("round-trips tab and drawer state through the URL", async () => {
    mockFetch(makeCase());
    renderCase("/cases/app-1?tab=evidence&feature=monthly_inflow_cv");
    await screen.findByText("APPROVE_STARTER");

    // ...with the drawer already open on the named feature.
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("population CV of monthly income")).toBeInTheDocument();
    // Pasted URL also lands on the Evidence tab (behind the modal, so hidden:true).
    expect(screen.getByRole("tab", { name: "Evidence", hidden: true })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("shows NO DECISION — SYSTEM UNAVAILABLE when an assessment failed", async () => {
    mockFetch(
      makeCase({
        decision: null,
        assessment_failed: true,
        assessments: {},
        blocking_tab: "evidence",
        chips: {
          pd: { value: null, status: "unavailable" },
          coverage: { score: null, band: null, status: "unavailable" },
          affordability: { status: "UNAVAILABLE", headroom_paise: null },
          verification: "UNAVAILABLE",
        },
      }),
    );
    renderCase("/cases/app-1");
    expect(await screen.findByText("NO DECISION — SYSTEM UNAVAILABLE")).toBeInTheDocument();
  });

  it("shows the consent-revoked and stale banners", async () => {
    mockFetch(makeCase({ consent_status: "REVOKED", stale: { is_stale: true, new_event_count: 3 } }));
    renderCase("/cases/app-1");
    expect(
      await screen.findByText(/this decision remains readable as of/),
    ).toBeInTheDocument();
    expect(screen.getByText(/3 new event\(s\) arrived after this decision/)).toBeInTheDocument();
  });

  it("renders a 404 case-not-found state, not a blank screen", async () => {
    mockFetch(null, 404);
    renderCase("/cases/missing");
    expect(await screen.findByText("Case not found")).toBeInTheDocument();
  });
});
