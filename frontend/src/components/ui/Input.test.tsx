import { render, screen } from "@testing-library/react";

import { Input } from "./Input";

describe("Input", () => {
  it("is valid by default", () => {
    render(<Input aria-label="Email" />);
    expect(screen.getByLabelText("Email")).not.toHaveAttribute("aria-invalid");
  });

  it("exposes aria-invalid when invalid", () => {
    render(<Input invalid aria-label="Email" />);
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
  });
});
