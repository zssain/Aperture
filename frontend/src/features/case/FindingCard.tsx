import { useState } from "react";

import { Icon } from "../../components/ui/Icon";
import { StatusDot } from "../../components/ui/StatusDot";
import type { Tone } from "../../components/ui/tones";
import { cn } from "../../lib/cn";
import { formatDate, formatPaise } from "../../lib/format";
import type { ManipulationFinding } from "./useCase";

const DETECTOR_LABELS: Record<string, string> = {
  D1: "Circular flow",
  D2: "Inflow burst",
  D3: "Counterparty concentration",
  D4: "Round-number salary",
  D5: "Balance arithmetic",
  D6: "Document provenance",
  D7: "Account age mismatch",
  D8: "Cross-applicant reuse",
};

const SEVERITY_TONE: Record<string, Tone> = {
  LOW: "neutral",
  MEDIUM: "caution",
  HIGH: "negative",
  CRITICAL: "negative",
};

/** An expandable finding. Collapsed shows the severity, detector and the arithmetic statement.
 * Expanded shows the cited transactions INLINE (never a modal) so the reviewer can compare the
 * statement against the rows it was computed from. */
export function FindingCard({ finding }: { finding: ManipulationFinding }) {
  const [open, setOpen] = useState(false);
  const label = DETECTOR_LABELS[finding.detector_id] ?? finding.detector_id;
  const tone = SEVERITY_TONE[finding.severity] ?? "neutral";

  return (
    <div className="rounded border border-border">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex w-full items-center justify-between gap-3 px-3 py-2 text-left",
          "hover:bg-sunken focus:outline-none focus-visible:ring-2 focus-visible:ring-accent",
        )}
      >
        <span className="flex items-center gap-3">
          <StatusDot tone={tone} label={finding.severity} />
          <span className="font-medium text-ink">{label}</span>
          <span className="text-sm text-muted">{finding.statement}</span>
        </span>
        <Icon name={open ? "chevron-up" : "chevron-down"} size={16} className="text-muted" />
      </button>

      {open ? (
        <div className="border-t border-border px-3 py-2">
          <p className="mb-2 text-xs uppercase tracking-wide text-muted">
            Cited transactions ({finding.cited_events.length})
          </p>
          {finding.cited_events.length === 0 ? (
            <p className="text-sm text-muted">No transaction rows are attached to this finding.</p>
          ) : (
            <table className="w-full border-collapse text-sm">
              <caption className="sr-only">Transactions cited by {label}</caption>
              <thead>
                <tr className="text-muted">
                  <th scope="col" className="py-1 text-left font-medium">Date</th>
                  <th scope="col" className="py-1 text-left font-medium">Description</th>
                  <th scope="col" className="py-1 text-right font-medium">Amount</th>
                  <th scope="col" className="py-1 text-right font-medium">Balance</th>
                </tr>
              </thead>
              <tbody>
                {finding.cited_events.map((event) => (
                  <tr key={event.id} className="border-t border-border">
                    <td className="py-1 text-left text-ink">{formatDate(event.occurred_at)}</td>
                    <td className="py-1 text-left text-ink">{event.description ?? "—"}</td>
                    <td className="py-1 text-right tabular-nums text-ink">
                      {event.amount_paise !== null ? formatPaise(event.amount_paise) : "—"}
                    </td>
                    <td className="py-1 text-right tabular-nums text-muted">
                      {event.balance_paise !== null ? formatPaise(event.balance_paise) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {Object.keys(finding.values).length > 0 ? (
            <p className="mt-2 text-xs text-muted">
              Triggering values:{" "}
              {Object.entries(finding.values)
                .map(([key, value]) => `${key.replace(/_/g, " ")} = ${String(value)}`)
                .join(" · ")}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
