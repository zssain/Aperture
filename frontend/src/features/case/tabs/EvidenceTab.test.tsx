import { describe, expect, it } from "vitest";

import type { EvidenceEvent } from "../useCase";
import { aggregate } from "./EvidenceTab";

function event(partial: Partial<EvidenceEvent>): EvidenceEvent {
  return {
    id: crypto.randomUUID(),
    occurred_at: "2026-08-01T10:00:00Z",
    direction: "CREDIT",
    amount_paise: 100_000,
    balance_paise: null,
    description: "test",
    category: "SALARY",
    confidence: 0.9,
    ...partial,
  };
}

describe("EvidenceTab aggregate", () => {
  it("sums real amounts into monthly inflow/outflow buckets", () => {
    const points = aggregate([
      event({ occurred_at: "2026-08-01T10:00:00Z", direction: "CREDIT", amount_paise: 500_000 }),
      event({ occurred_at: "2026-08-05T10:00:00Z", direction: "DEBIT", amount_paise: 200_000 }),
    ]);
    expect(points).toHaveLength(1);
    expect(points[0]).toMatchObject({ month: "2026-08", inflow_paise: 500_000, outflow_paise: 200_000 });
  });

  it("never fabricates a ₹0 for a null amount — missing data is excluded, not summed", () => {
    // A null-amount event is a data gap (rendered as "—" in the table); it must not
    // silently contribute 0 to the cash-flow chart (invariant: never invent a number).
    const points = aggregate([
      event({ occurred_at: "2026-08-01T10:00:00Z", direction: "CREDIT", amount_paise: 500_000 }),
      event({ occurred_at: "2026-08-10T10:00:00Z", direction: "CREDIT", amount_paise: null }),
    ]);
    expect(points).toHaveLength(1);
    expect(points[0]?.inflow_paise).toBe(500_000); // the null did not add a phantom 0
  });

  it("drops a month that has only null-amount events rather than showing it as ₹0 flow", () => {
    const points = aggregate([
      event({ occurred_at: "2026-07-01T10:00:00Z", direction: "CREDIT", amount_paise: null }),
    ]);
    expect(points).toHaveLength(0);
  });
});
