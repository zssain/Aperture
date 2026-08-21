import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ANALYST_SESSION, renderWithProviders } from "../../test/utils";
import { QueuePage } from "./QueuePage";
import type { QueuePage as QueuePageData, QueueRow } from "./useQueue";

function row(overrides: Partial<QueueRow>): QueueRow {
  return {
    id: "d1",
    application_id: "app-1",
    applicant_name: "Asha Kumar",
    applicant_ref: "EXT-001",
    amount_paise: 10_000_000,
    routed_because: { text: "Coverage 41 (min 55)", rule_number: 4 },
    recommendation: {
      action: "REFER",
      band: null,
      approved_limit_paise: null,
      tenor_months: 12,
      annual_rate_bps: 1800,
    },
    pd: { value: 0.187, status: "uncalibrated" },
    coverage: { value: 41, status: "measured" },
    verification: "CLEAR",
    waiting_seconds: 7200,
    decided_at: "2026-08-20T10:00:00Z",
    ...overrides,
  };
}

function page(overrides: Partial<QueuePageData>): QueuePageData {
  return {
    view: "my-exceptions",
    counts: { "my-exceptions": 2, "evidence-needed": 1, "all-decisions": 5 },
    rows: [
      row({ id: "d1" }),
      row({
        id: "d2",
        application_id: "app-2",
        applicant_name: "Ravi Nair",
        routed_because: { text: "Verification ELEVATED · circular flow ×3", rule_number: 5 },
        pd: { value: 0.05, status: "measured" },
        verification: "ELEVATED",
      }),
    ],
    next_cursor: null,
    auto_decided_24h: 42,
    ...overrides,
  };
}

function mockFetch(data: QueuePageData, status = 200): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(status === 200 ? data : { detail: { code: "ERR", message: "boom" } }), {
      status,
      headers: { "content-type": "application/json", "X-Correlation-ID": "cid-test" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

afterEach(() => vi.unstubAllGlobals());

describe("QueuePage", () => {
  it("renders rows with routed_because and tab counts", async () => {
    mockFetch(page({}));
    renderWithProviders(<QueuePage />, {
      route: "/queue?view=my-exceptions",
      session: ANALYST_SESSION,
    });

    expect(await screen.findByText("Coverage 41 (min 55)")).toBeInTheDocument();
    expect(screen.getByText("Verification ELEVATED · circular flow ×3")).toBeInTheDocument();
    // Tab carries its own count; the fraud view is absent for an analyst.
    expect(screen.getByRole("tab", { name: /My exceptions \(2\)/ })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /Fraud review/ })).not.toBeInTheDocument();
  });

  it("shows a transition badge inside the existing recommendation column", async () => {
    mockFetch(
      page({
        view: "newly-eligible",
        counts: { "newly-eligible": 1, deterioration: 0, "all-decisions": 5 },
        rows: [
          row({
            change: {
              direction: "IMPROVED",
              previous_band: "DECLINE",
              new_band: "STARTER",
              previous_outcome: "DECLINE_RISK",
              new_outcome: "APPROVE_STARTER",
              human_action_protected: false,
            },
          }),
        ],
      }),
    );
    const { container } = renderWithProviders(<QueuePage />, {
      route: "/queue?view=newly-eligible",
      session: ANALYST_SESSION,
    });
    expect(await screen.findByText(/DECLINE → STARTER/)).toBeInTheDocument();
    const headers = Array.from(container.querySelectorAll("th")).map((header) => header.textContent);
    expect(headers).toEqual([
      "Applicant",
      "Amount",
      "Sources",
      "Routed because",
      "Recommendation",
      "PD",
      "Coverage",
      "Verification",
      "Waiting",
    ]);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("renders an uncalibrated PD as neutral with an UNCAL marker", async () => {
    mockFetch(page({}));
    const { container } = renderWithProviders(<QueuePage />, {
      route: "/queue?view=my-exceptions",
      session: ANALYST_SESSION,
    });
    await screen.findByText("Coverage 41 (min 55)");
    expect(screen.getAllByText("UNCAL").length).toBeGreaterThan(0);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows the success empty state with the 24h auto-decision count", async () => {
    mockFetch(page({ rows: [], auto_decided_24h: 42 }));
    renderWithProviders(<QueuePage />, {
      route: "/queue?view=my-exceptions",
      session: ANALYST_SESSION,
    });
    expect(await screen.findByText("Nothing needs review")).toBeInTheDocument();
    expect(screen.getByText(/42 decisions were made automatically/)).toBeInTheDocument();
  });

  it("shows a distinct zero-results state that names the active filters", async () => {
    mockFetch(page({ rows: [] }));
    renderWithProviders(<QueuePage />, {
      route: "/queue?view=my-exceptions&q=zzz",
      session: ANALYST_SESSION,
    });
    expect(await screen.findByText("No cases match these filters")).toBeInTheDocument();
    expect(screen.getByText(/search "zzz"/)).toBeInTheDocument();
  });

  it("round-trips filter + view state from the URL", async () => {
    const fetchMock = mockFetch(page({ view: "evidence-needed" }));
    renderWithProviders(<QueuePage />, {
      route: "/queue?view=evidence-needed&q=asha&band=ELEVATED&cmin=40",
      session: ANALYST_SESSION,
    });
    await screen.findByText("Coverage 41 (min 55)");

    expect(screen.getByLabelText("Search")).toHaveValue("asha");
    expect(screen.getByLabelText("Verification")).toHaveValue("ELEVATED");
    expect(screen.getByLabelText("Coverage minimum")).toHaveValue(40);

    const requested = String(fetchMock.mock.calls[0]?.[0]);
    expect(requested).toContain("view=evidence-needed");
    expect(requested).toContain("q=asha");
    expect(requested).toContain("band=ELEVATED");
    expect(requested).toContain("coverage_min=40");
  });

  it("supports j/k navigation and opens the case on Enter", async () => {
    mockFetch(page({}));
    const { container } = renderWithProviders(
      <>
        <QueuePage />
        <LocationProbe />
      </>,
      { route: "/queue?view=my-exceptions", session: ANALYST_SESSION },
    );
    await screen.findByText("Coverage 41 (min 55)");

    const bodyRows = container.querySelectorAll<HTMLTableRowElement>("tbody tr");
    expect(bodyRows).toHaveLength(2);
    const firstRow = bodyRows[0] as HTMLTableRowElement;
    const secondRow = bodyRows[1] as HTMLTableRowElement;

    firstRow.focus();
    expect(firstRow).toHaveFocus();
    await userEvent.keyboard("j");
    expect(secondRow).toHaveFocus();
    await userEvent.keyboard("k");
    expect(firstRow).toHaveFocus();

    await userEvent.keyboard("{Enter}");
    expect(screen.getByTestId("location")).toHaveTextContent("/cases/app-1");
  });

  it("cmd-click opens the case in a new tab", async () => {
    mockFetch(page({}));
    const openSpy = vi.fn();
    vi.stubGlobal("open", openSpy);
    renderWithProviders(<QueuePage />, {
      route: "/queue?view=my-exceptions",
      session: ANALYST_SESSION,
    });
    await screen.findByText("Coverage 41 (min 55)");

    // Cmd/Ctrl-click behaves like a link: open the case in a new tab.
    fireEvent.click(screen.getByText("Coverage 41 (min 55)"), { metaKey: true });

    expect(openSpy).toHaveBeenCalledWith("/cases/app-1", "_blank", "noopener");
  });

  it("renders an error state when the queue fails to load", async () => {
    mockFetch(page({}), 500);
    renderWithProviders(<QueuePage />, {
      route: "/queue?view=my-exceptions",
      session: ANALYST_SESSION,
    });
    expect(await screen.findByText("Could not load the queue")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
