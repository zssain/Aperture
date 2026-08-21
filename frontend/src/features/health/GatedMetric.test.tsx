import { render, screen } from "@testing-library/react";
import { GatedMetric } from "./GatedMetric";

describe("GatedMetric", () => {
  it("never renders an unearned value", () => {
    render(<GatedMetric metric={{ status: "INSUFFICIENT_SAMPLE", value: null, ci_low: null, ci_high: null, n: 17, minimum_n: 200, reason: "Insufficient sample (n=17, minimum 200)." }} />);
    expect(screen.getByText(/INSUFFICIENT SAMPLE/).parentElement).toHaveTextContent("n=17, minimum 200");
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("renders a measured number with its interval", () => {
    render(<GatedMetric metric={{ status: "MEASURED", value: .2, ci_low: .1, ci_high: .3, n: 200, minimum_n: 200, reason: null }} />);
    expect(screen.getByText("0.200")).toBeInTheDocument();
    expect(screen.getByText(/95% CI/)).toBeVisible();
  });
});
