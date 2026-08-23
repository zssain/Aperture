import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "../../test/utils";
import { HomePage } from "./HomePage";

describe("HomePage", () => {
  it("renders the hero, both CTAs, and the primary landmarks", () => {
    renderWithProviders(<HomePage />, { route: "/" });
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/credit bureaus can/i);
    // Two sign-in CTAs (header + hero) plus the closing one all point at /signin.
    const signInLinks = screen.getAllByRole("link", { name: /sign in|enter the workspace/i });
    expect(signInLinks.length).toBeGreaterThanOrEqual(2);
    for (const link of signInLinks) expect(link).toHaveAttribute("href", "/signin");
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
  });

  it("only quotes numbers that are true to the architecture (no invented stats)", () => {
    renderWithProviders(<HomePage />, { route: "/" });
    expect(screen.getByText(/9-gate ladder/i)).toBeInTheDocument();
    expect(screen.getByText(/Eight fraud detectors/i)).toBeInTheDocument();
    expect(screen.getByText(/D1.{0,3}D8/i)).toBeInTheDocument();
    expect(screen.getByText(/Four assessments/i)).toBeInTheDocument();
  });

  it("states the honesty promise verbatim", () => {
    renderWithProviders(<HomePage />, { route: "/" });
    expect(screen.getByText(/We never invent a number\. When we don.t know, we say so\./i)).toBeInTheDocument();
  });
});
