import { render, screen } from "@testing-library/react";

import { StatusDot } from "./StatusDot";

describe("StatusDot", () => {
  it("renders the required label; the dot is decorative (aria-hidden)", () => {
    const { container } = render(<StatusDot tone="negative" label="Declined" />);
    expect(screen.getByText("Declined")).toBeInTheDocument();
    const dot = container.querySelector("[aria-hidden='true']");
    expect(dot?.className).toContain("bg-negative");
  });
});
