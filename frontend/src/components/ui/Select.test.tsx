import { render, screen } from "@testing-library/react";

import { Select } from "./Select";

describe("Select", () => {
  it("renders options and reflects the selected value", () => {
    render(
      <Select aria-label="Role" defaultValue="a">
        <option value="a">A</option>
        <option value="b">B</option>
      </Select>,
    );
    const select = screen.getByLabelText<HTMLSelectElement>("Role");
    expect(select.value).toBe("a");
  });

  it("supports an invalid state", () => {
    render(
      <Select invalid aria-label="Role">
        <option value="a">A</option>
      </Select>,
    );
    expect(screen.getByLabelText("Role")).toHaveAttribute("aria-invalid", "true");
  });
});
