import { render, screen } from "@testing-library/react";

import { Button } from "./Button";
import { EmptyState } from "./EmptyState";

describe("EmptyState", () => {
  it("renders title, description and one action", () => {
    render(
      <EmptyState
        title="No cases in your queue"
        description="Cases routed to a human appear here."
        action={<Button>Refresh</Button>}
      />,
    );
    expect(screen.getByText("No cases in your queue")).toBeInTheDocument();
    expect(
      screen.getByText("Cases routed to a human appear here."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refresh" })).toBeInTheDocument();
  });

  it("renders without an action", () => {
    render(<EmptyState title="Nothing" description="Empty" />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});
