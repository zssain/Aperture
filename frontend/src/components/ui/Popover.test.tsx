import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Popover } from "./Popover";

describe("Popover", () => {
  it("opens on trigger activation and reveals its content", async () => {
    render(
      <Popover trigger={<button type="button">Menu</button>}>
        <p>Panel content</p>
      </Popover>,
    );
    expect(screen.queryByText("Panel content")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Menu" }));
    expect(await screen.findByText("Panel content")).toBeInTheDocument();
  });
});
