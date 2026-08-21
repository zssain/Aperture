import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ErrorState } from "./ErrorState";

describe("ErrorState", () => {
  it("shows the message, correlation id and a working retry", async () => {
    const onRetry = vi.fn();
    render(
      <ErrorState message="Could not load" correlationId="cid-123" onRetry={onRetry} />,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Could not load")).toBeInTheDocument();
    expect(screen.getByText("cid-123")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("omits retry when it is not meaningful", () => {
    render(<ErrorState message="Fatal" />);
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
  });
});
