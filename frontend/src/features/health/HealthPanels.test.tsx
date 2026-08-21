import { render } from "@testing-library/react";
import { axe } from "jest-axe";
import { MemoryRouter } from "react-router-dom";

import { CalibrationPanel } from "./CalibrationPanel";
import { CoveragePanel } from "./CoveragePanel";
import { DisparityPanel } from "./DisparityPanel";
import { DriftPanel } from "./DriftPanel";
import type { MetricResult } from "./GatedMetric";
import { ModelCardPanel } from "./ModelCardPanel";
import { OverridePanel } from "./OverridePanel";

const unavailable: MetricResult = { status: "NOT_YET_MEASURABLE", value: null, ci_low: null, ci_high: null, n: 0, minimum_n: 200, reason: "200 closed outcomes are required; 0 exist." };

it("has no axe violations in the day-one gated state and keeps chart tables visible", async () => {
  const rendered = render(<MemoryRouter><div>
    <CalibrationPanel asOf="2026-08-21" data={{ model_a: { brier: unavailable, reliability: [] }, model_b: unavailable, discrimination: { auc: unavailable, ks: unavailable } }} />
    <DriftPanel asOf="2026-08-21" data={{ overall: unavailable, threshold: .2, threshold_label: "Operational convention, not a law" }} />
    <CoveragePanel asOf="2026-08-21" data={{ histogram: [], review_evidence_share: unavailable }} />
    <OverridePanel asOf="2026-08-21" data={{ rate: unavailable, by_reason: {}, by_analyst: {}, control_chart: [], interpretation: "A sustained spike on one reason code is a policy bug report.", policy_studio_url: "/policy" }} />
    <DisparityPanel asOf="2026-08-21" data={{}} />
    <ModelCardPanel asOf="2026-08-21" />
  </div></MemoryRouter>);
  expect(rendered.getByText("Reliability curve data table")).toBeVisible();
  expect(rendered.getByText("Control chart data table")).toBeVisible();
  expect(await axe(rendered.container)).toHaveNoViolations();
});
