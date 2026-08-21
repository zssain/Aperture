import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { afterEach } from "vitest";

import { renderWithProviders } from "../../test/utils";
import { SignInPage } from "./SignInPage";

afterEach(() => vi.unstubAllGlobals());

describe("SignInPage", () => {
  it("has no axe violations", async () => {
    const { container } = renderWithProviders(<SignInPage />, {
      route: "/signin",
      session: null,
    });
    expect(await axe(container)).toHaveNoViolations();
  });

  it("posts credentials to the login endpoint on submit", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          user_id: "1",
          email: "a@b.com",
          full_name: "A B",
          role: "CREDIT_ANALYST",
          tenant_id: "t",
          tenant_name: "Acme",
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<SignInPage />, { route: "/signin", session: null });

    await userEvent.type(screen.getByLabelText("Email"), "a@b.com");
    await userEvent.type(screen.getByLabelText("Password"), "secret");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/auth/login",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
