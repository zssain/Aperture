import { render, screen } from "@testing-library/react";

import { Drawer } from "./Drawer";

describe("Drawer", () => {
  it("renders title and content when open", () => {
    render(
      <Drawer open onOpenChange={() => undefined} title="Case details">
        <p>Body content</p>
      </Drawer>,
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Case details")).toBeInTheDocument();
    expect(screen.getByText("Body content")).toBeInTheDocument();
  });

  it("renders nothing when closed", () => {
    render(
      <Drawer open={false} onOpenChange={() => undefined} title="Hidden">
        <p>Body</p>
      </Drawer>,
    );
    expect(screen.queryByText("Body")).toBeNull();
  });
});
