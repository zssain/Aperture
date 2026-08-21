import { render, screen } from "@testing-library/react";

import { Modal } from "./Modal";

describe("Modal", () => {
  it("renders title, body and footer when open", () => {
    render(
      <Modal
        open
        onOpenChange={() => undefined}
        title="Confirm"
        footer={<button type="button">Proceed</button>}
      >
        <p>Are you sure?</p>
      </Modal>,
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Confirm")).toBeInTheDocument();
    expect(screen.getByText("Are you sure?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Proceed" })).toBeInTheDocument();
  });

  it("renders nothing when closed", () => {
    render(
      <Modal open={false} onOpenChange={() => undefined} title="Hidden">
        <p>Body</p>
      </Modal>,
    );
    expect(screen.queryByText("Body")).toBeNull();
  });
});
