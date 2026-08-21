import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { describe, expect, it } from "vitest";

import { ChangeBadge } from "./ChangeBadge";

describe("ChangeBadge", () => {
  it("renders the exact decision transition with an accessible direction", async () => {
    const { container } = render(
      <ChangeBadge
        change={{
          direction: "IMPROVED",
          previous_band: "DECLINE",
          new_band: "STARTER",
          previous_outcome: "DECLINE_RISK",
          new_outcome: "APPROVE_STARTER",
          human_action_protected: false,
        }}
      />,
    );
    expect(screen.getByText(/DECLINE → STARTER/)).toBeInTheDocument();
    expect(screen.getByText("Improved decision:")).toHaveClass("sr-only");
    expect(await axe(container)).toHaveNoViolations();
  });
});
