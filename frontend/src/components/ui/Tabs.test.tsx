import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import { Tabs } from "./Tabs";

function Harness() {
  const [value, setValue] = useState("a");
  return (
    <Tabs
      ariaLabel="Sections"
      value={value}
      onValueChange={setValue}
      items={[
        { value: "a", label: "Evidence" },
        { value: "b", label: "Assessment" },
      ]}
    />
  );
}

describe("Tabs", () => {
  it("marks the selected tab and switches on click", async () => {
    render(<Harness />);
    expect(screen.getByRole("tab", { name: "Evidence" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await userEvent.click(screen.getByRole("tab", { name: "Assessment" }));
    expect(screen.getByRole("tab", { name: "Assessment" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("moves selection with arrow keys", async () => {
    render(<Harness />);
    const first = screen.getByRole("tab", { name: "Evidence" });
    first.focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Assessment" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });
});
