import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../../test/utils";
import { ArchitectureAssistant } from "./ArchitectureAssistant";
import { ExplainDecisionPanel } from "./ExplainDecisionPanel";

function mockJson(data: unknown, status = 200): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(status === 200 ? data : { detail: { code: "ERR", message: "boom" } }), {
      status,
      headers: { "content-type": "application/json", "X-Correlation-ID": "cid-test" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("ExplainDecisionPanel", () => {
  it("posts the question and renders the grounded answer with citations", async () => {
    const fetchMock = mockJson({
      answer: "Declined by rule pd_decline.",
      citations: [{ label: "Decision", detail: "DECLINE · rule: pd_decline", tab: "decision" }],
      used_llm: true,
    });

    renderWithProviders(<ExplainDecisionPanel applicationId="app-1" />);

    await userEvent.click(screen.getByRole("button", { name: /Why was this decided/i }));

    expect(await screen.findByText("Declined by rule pd_decline.")).toBeInTheDocument();
    expect(screen.getByText(/DECLINE · rule: pd_decline/)).toBeInTheDocument();
    expect(screen.getByText(/AI-phrased over grounded facts/)).toBeInTheDocument();

    const call = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(String(call[0])).toContain("/api/v1/cases/app-1/explain");
    expect(JSON.parse(call[1].body as string)).toMatchObject({
      question: expect.stringMatching(/why/i),
    });
  });

  it("labels a deterministic (LLM-off) answer honestly", async () => {
    mockJson({ answer: "Declined on affordability.", citations: [], used_llm: false });
    renderWithProviders(<ExplainDecisionPanel applicationId="app-1" />);
    await userEvent.click(screen.getByRole("button", { name: /biggest risk factors/i }));
    expect(await screen.findByText(/Declined on affordability/)).toBeInTheDocument();
    expect(screen.getByText(/LLM off/)).toBeInTheDocument();
  });
});

describe("ArchitectureAssistant", () => {
  it("opens on the launcher and cites real file paths", async () => {
    mockJson({
      answer: "The risk model lives in the scorecard.",
      citations: [
        { title: "Risk model (PD)", paths: ["backend/app/services/risk/service.py"] },
      ],
      used_llm: true,
    });

    renderWithProviders(<ArchitectureAssistant />);

    fireEvent.click(screen.getByRole("button", { name: /Ask about the architecture/i }));
    await userEvent.click(screen.getByRole("button", { name: /Where is the risk model/i }));

    await waitFor(() =>
      expect(screen.getByText("The risk model lives in the scorecard.")).toBeInTheDocument(),
    );
    expect(screen.getByText("backend/app/services/risk/service.py")).toBeInTheDocument();
  });
});
