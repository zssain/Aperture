import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { InfoHint } from "./InfoHint";

describe("InfoHint", () => {
  it("opens a full explainer: what it is, how it's calculated, the formula, and a caveat", async () => {
    render(<InfoHint term="pd" />);
    // Keyboard/click reachable via a real labelled button.
    await userEvent.click(screen.getByRole("button", { name: /what is probability of default/i }));

    expect(await screen.findByText(/Probability of default \(PD\)/)).toBeInTheDocument();
    expect(screen.getByText(/How it.s calculated/i)).toBeInTheDocument();
    expect(screen.getByText(/Formula/)).toBeInTheDocument();
    expect(screen.getByText(/PD = 1 \/ \(1 \+ e/)).toBeInTheDocument();
    // The honest caveat is always shown for an uncalibrated score.
    expect(screen.getByText(/UNCALIBRATED/)).toBeInTheDocument();
  });

  it("renders only the sections an entry provides (no empty scaffolding)", async () => {
    render(<InfoHint term="headroom" />);
    await userEvent.click(screen.getByRole("button", { name: /what is headroom/i }));
    await screen.findByText(/Headroom/);
    // Headroom has a formula but no "how it's calculated" prose — that section is absent.
    expect(screen.getByText(/Formula/)).toBeInTheDocument();
    expect(screen.queryByText(/How it.s calculated/i)).toBeNull();
  });
});
