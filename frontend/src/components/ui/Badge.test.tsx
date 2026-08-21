import { render, screen } from "@testing-library/react";

import { Badge } from "./Badge";

describe("Badge", () => {
  it("renders content with the tone colour", () => {
    render(<Badge tone="positive">Approved</Badge>);
    expect(screen.getByText("Approved").className).toContain("text-positive");
  });

  it("defaults to the neutral tone", () => {
    render(<Badge>Draft</Badge>);
    expect(screen.getByText("Draft").className).toContain("text-neutral");
  });
});
