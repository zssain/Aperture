import { screen } from "@testing-library/react";
import { axe } from "jest-axe";

import { ANALYST_SESSION, renderWithProviders } from "../../test/utils";
import { AppRoutes } from "../../routes";

describe("AppShell + nav", () => {
  it("renders the shell, hides Policy from an analyst, and has no axe violations", async () => {
    const { container } = renderWithProviders(<AppRoutes />, {
      route: "/queue",
      session: ANALYST_SESSION,
    });

    expect(screen.getByText("APERTURE")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Queue" })).toBeInTheDocument();
    // A role without Policy access never renders the nav item (absent, not disabled).
    expect(screen.queryByRole("link", { name: "Policy" })).toBeNull();

    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows a purpose-built screen when the role is not allowed", () => {
    renderWithProviders(<AppRoutes />, {
      route: "/policy",
      session: ANALYST_SESSION,
    });
    expect(
      screen.getByText("Permission denied"),
    ).toBeInTheDocument();
  });
});
