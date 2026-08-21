import { render, screen } from "@testing-library/react";

import { Chip } from "./Chip";

describe("Chip", () => {
  it("renders as a pill with the tone colour", () => {
    render(<Chip tone="neutral">UNCAL</Chip>);
    const chip = screen.getByText("UNCAL");
    expect(chip.className).toContain("rounded-pill");
    expect(chip.className).toContain("text-neutral");
  });
});
