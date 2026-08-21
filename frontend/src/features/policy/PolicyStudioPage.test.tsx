import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { MemoryRouter } from "react-router-dom";
import { RuleEditor } from "./RuleEditor";
import { SimulationReport } from "./SimulationReport";
import type { PolicyRules } from "./usePolicy";

const rules: PolicyRules = {
  policy_version: "policy-v2", min_coverage: 40, pd_decline_threshold: .25,
  pd_enhanced: .08, pd_standard: .15, cov_high: 75, cov_mid: 55,
  mandatory_review_ceiling_paise: 20_000_000, exploration_margin: .03,
  exploration_budget: .05,
  terms: { APPROVE_STARTER: { max_principal_paise: 5_000_000, max_tenor_months: 12, rate_band: "C", annual_rate_bps: 2200 } },
};

describe("Policy Studio components", () => {
  it("puts a specific validator failure at the numeric field", () => {
    render(<RuleEditor rules={{ ...rules, cov_mid: 90 }} live={rules} errors={["cov_mid (90) must be < cov_high (75)"]} onChange={() => undefined} />);
    const input = screen.getByLabelText(/Mid coverage/);
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText(/must be < cov_high/)).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /json/i })).not.toBeInTheDocument();
  });

  it("keeps the uncalibrated caveat adjacent and has no axe violations", async () => {
    const { container } = render(<MemoryRouter><SimulationReport report={{ job_id: "j", status: "SUCCEEDED", draft_hash: "h", n_snapshots: 1000, approval_delta: .01, cohort_deltas: {}, transition_matrix: { "DECLINE->APPROVE": 10 }, modelled_bad_rate_delta: -.01, expected_loss_delta: -.02, caveats: ["Loss estimates inherit the cash-flow scorecard's UNCALIBRATED status and are directional only."], largest_flips: [] }} /></MemoryRouter>);
    const loss = screen.getByText(/Expected-loss delta/);
    expect(loss.parentElement).toHaveTextContent("UNCALIBRATED");
    expect(await axe(container)).toHaveNoViolations();
  });
});
