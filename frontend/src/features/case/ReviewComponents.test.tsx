import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../../test/utils";
import { FindingCard } from "./FindingCard";
import { NoticePreview } from "./NoticePreview";
import { OverrideModal } from "./OverrideModal";
import { ReplayPanel } from "./ReplayPanel";
import type { ManipulationFinding } from "./useCase";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "X-Correlation-ID": "cid" },
  });
}

afterEach(() => vi.unstubAllGlobals());

// --------------------------------------------------------------------------- #
// Override modal: validation, submit gating, Esc-confirm on a dirty form, axe.
// --------------------------------------------------------------------------- #
describe("OverrideModal", () => {
  function setup(onOpenChange = vi.fn(), onSubmit = vi.fn()) {
    renderWithProviders(
      <OverrideModal
        decisionId="d1"
        recommendation="APPROVE STANDARD"
        open
        onOpenChange={onOpenChange}
        onSubmit={onSubmit}
        submitting={false}
      />,
    );
    return { onOpenChange, onSubmit };
  }

  it("keeps submit disabled until an outcome, a reason code and 20+ chars are present", async () => {
    const { onSubmit } = setup();
    const submit = screen.getByRole("button", { name: "Submit override" });
    expect(submit).toBeDisabled();

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Outcome" }), "DECLINED");
    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: "Reason code" }),
      "DOCUMENT_REVIEW",
    );
    // Under 20 characters → still disabled.
    await userEvent.type(screen.getByRole("textbox"), "too short");
    expect(submit).toBeDisabled();

    await userEvent.clear(screen.getByRole("textbox"));
    await userEvent.type(screen.getByRole("textbox"), "Declined after a manual document review.");
    expect(submit).toBeEnabled();

    await userEvent.click(submit);
    expect(onSubmit).toHaveBeenCalledWith({
      reason_code: "DOCUMENT_REVIEW",
      reason_text: "Declined after a manual document review.",
      override_outcome: "DECLINED",
    });
  });

  it("confirms before discarding a dirty form on Esc", async () => {
    const confirmSpy = vi.fn().mockReturnValue(true);
    vi.stubGlobal("confirm", confirmSpy);
    const { onOpenChange } = setup();

    await userEvent.type(screen.getByRole("textbox"), "Some typed reason text here.");
    await userEvent.keyboard("{Escape}");

    expect(confirmSpy).toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("has no axe violations and traps focus", async () => {
    const { container } = renderWithProviders(
      <OverrideModal
        decisionId="d1"
        recommendation="APPROVE STANDARD"
        open
        onOpenChange={vi.fn()}
        onSubmit={vi.fn()}
        submitting={false}
      />,
    );
    const dialog = await screen.findByRole("dialog");
    expect(dialog.contains(document.activeElement)).toBe(true);
    expect(await axe(container)).toHaveNoViolations();
  });
});

// --------------------------------------------------------------------------- #
// Finding expands inline to its cited transactions.
// --------------------------------------------------------------------------- #
describe("FindingCard", () => {
  const finding: ManipulationFinding = {
    detector_id: "D1",
    severity: "HIGH",
    statement: "Circular flow detected across 3 transfers.",
    cited_event_ids: ["e1", "e2", "e3"],
    confidence: 0.9,
    values: { transfers: 3 },
    cited_events: [
      { id: "e1", occurred_at: "2026-07-01T00:00:00Z", direction: "CREDIT", amount_paise: 500000, balance_paise: 100000, description: "transfer in" },
      { id: "e2", occurred_at: "2026-07-02T00:00:00Z", direction: "DEBIT", amount_paise: 500000, balance_paise: 50000, description: "transfer out" },
      { id: "e3", occurred_at: "2026-07-03T00:00:00Z", direction: "CREDIT", amount_paise: 500000, balance_paise: 90000, description: "transfer in" },
    ],
  };

  it("expands inline to show the cited transactions matching cited_event_ids", async () => {
    renderWithProviders(<FindingCard finding={finding} />);
    const toggle = screen.getByRole("button", { name: /Circular flow/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");

    const table = screen.getByRole("table");
    const bodyRows = within(table).getAllByRole("row").slice(1); // minus header
    expect(bodyRows).toHaveLength(finding.cited_event_ids.length);
    expect(within(table).getByText("transfer out")).toBeInTheDocument();
    expect(within(table).getAllByText("transfer in")).toHaveLength(2);
  });
});

// --------------------------------------------------------------------------- #
// Replay: IDENTICAL (positive) and DIVERGED (diff table + alert).
// --------------------------------------------------------------------------- #
describe("ReplayPanel", () => {
  it("renders IDENTICAL as a pass", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        json({ status: "IDENTICAL", diff: {}, recomputed_outcome: "APPROVE_STANDARD", recomputed_action: "APPROVE", stored_action: "APPROVE", policy_version_id: "p", counterfactual: false, reused_risk: true }),
      ),
    );
    renderWithProviders(<ReplayPanel decisionId="d1" />);
    await userEvent.click(screen.getByRole("button", { name: "Replay decision" }));
    expect(await screen.findByText("IDENTICAL")).toBeInTheDocument();
    expect(screen.getByText(/reproduced exactly/)).toBeInTheDocument();
  });

  it("renders DIVERGED prominently with a field-level diff", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        json({
          status: "DIVERGED",
          diff: { action: { stored: "APPROVE", recomputed: "DECLINE" } },
          recomputed_outcome: "DECLINE_RISK", recomputed_action: "DECLINE",
          stored_action: "APPROVE", policy_version_id: "p", counterfactual: false, reused_risk: false,
        }),
      ),
    );
    renderWithProviders(<ReplayPanel decisionId="d1" />);
    await userEvent.click(screen.getByRole("button", { name: "Replay decision" }));
    expect(await screen.findByText("DIVERGED")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/must not be treated as a pass/);
    expect(screen.getByText("action")).toBeInTheDocument();
  });
});

// --------------------------------------------------------------------------- #
// NoticePreview: language switch renders the same notice in another language.
// --------------------------------------------------------------------------- #
describe("NoticePreview", () => {
  it("switches language and re-renders the applicant notice", async () => {
    const fetchMock = vi.fn(async (url: string | URL) => {
      const hi = String(url).includes("language=hi");
      return json({
        subject: hi ? "आपका नोटिस" : "Your notice",
        body: hi ? "यह हिन्दी में है" : "This is in English",
        language: hi ? "hi" : "en",
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(<NoticePreview decisionId="d1" kind="recourse" />);
    expect(await screen.findByText("This is in English")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "हिन्दी" }));
    await waitFor(() => expect(screen.getByText("यह हिन्दी में है")).toBeInTheDocument());
  });
});
