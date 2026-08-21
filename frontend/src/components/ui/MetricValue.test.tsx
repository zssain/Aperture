import { render, screen } from "@testing-library/react";

import { MetricValue } from "./MetricValue";

describe("MetricValue", () => {
  it("renders a measured value in ink (never a semantic colour)", () => {
    render(<MetricValue value={42} status="measured" />);
    const el = screen.getByText("42");
    expect(el.className).toContain("text-ink");
    expect(el.className).not.toContain("text-positive");
  });

  it("renders uncalibrated in neutral grey with an UNCAL marker, never green", () => {
    const { container } = render(
      <MetricValue value={0.73} status="uncalibrated" precision={2} />,
    );
    expect(screen.getByText("UNCAL")).toBeInTheDocument();
    const wrapper = container.firstElementChild;
    expect(wrapper?.className).toContain("text-neutral");
    expect(container.innerHTML).not.toContain("text-positive");
  });

  it("renders unavailable as an em-dash and never a zero", () => {
    render(<MetricValue value={null} status="unavailable" />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    expect(screen.queryByText("0")).toBeNull();
  });

  it("shows the sample size for insufficient_sample", () => {
    render(<MetricValue value={null} status="insufficient_sample" sampleSize={7} />);
    expect(screen.getByText("Insufficient sample (n=7)")).toBeInTheDocument();
  });
});
