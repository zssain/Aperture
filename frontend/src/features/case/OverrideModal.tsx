import { useEffect, useState } from "react";

import { Button } from "../../components/ui/Button";
import { Icon } from "../../components/ui/Icon";
import { Modal } from "../../components/ui/Modal";
import { Select } from "../../components/ui/Select";
import { cn } from "../../lib/cn";
import {
  MIN_REASON_LENGTH,
  REASON_CODES,
  type ReviewOutcome,
} from "./useReview";

const OUTCOMES: ReadonlyArray<{ value: ReviewOutcome; label: string }> = [
  { value: "APPROVED", label: "Approve" },
  { value: "DECLINED", label: "Decline" },
  { value: "ESCALATED", label: "Escalate" },
];

export interface OverrideSubmission {
  reason_code: string;
  reason_text: string;
  override_outcome: ReviewOutcome;
}

/** The override modal — one of only two modals in the product. It shows the system's
 * recommendation beside the chosen outcome so the divergence is visible, and requires a reason
 * code and >= 20 characters of free text before Submit enables (invariant 10). The typed reason
 * is drafted to sessionStorage so a mid-form re-auth does not lose it. Esc confirms on a dirty
 * form before discarding. */
export function OverrideModal({
  decisionId,
  recommendation,
  open,
  onOpenChange,
  onSubmit,
  submitting,
  errorMessage,
}: {
  decisionId: string;
  recommendation: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (submission: OverrideSubmission) => void;
  submitting: boolean;
  errorMessage?: string;
}) {
  const draftKey = `aperture:override-draft:${decisionId}`;
  const [outcome, setOutcome] = useState<ReviewOutcome | "">("");
  const [reasonCode, setReasonCode] = useState("");
  const [reasonText, setReasonText] = useState("");

  // Restore any draft reason text when the modal opens (survives a re-auth redirect + return).
  useEffect(() => {
    if (!open) return;
    try {
      const saved = window.sessionStorage.getItem(draftKey);
      if (saved) setReasonText(saved);
    } catch {
      // sessionStorage unavailable — no draft to restore.
    }
  }, [open, draftKey]);

  function updateReasonText(value: string): void {
    setReasonText(value);
    try {
      window.sessionStorage.setItem(draftKey, value);
    } catch {
      // Best-effort draft; never block typing.
    }
  }

  const trimmed = reasonText.trim();
  const dirty = outcome !== "" || reasonCode !== "" || trimmed !== "";
  const valid = outcome !== "" && reasonCode !== "" && trimmed.length >= MIN_REASON_LENGTH;

  function handleOpenChange(next: boolean): void {
    if (!next && dirty) {
      // Esc / overlay on a dirty form confirms first (a native prompt, not a third modal).
      const discard = window.confirm("Discard your override reason?");
      if (!discard) return;
      try {
        window.sessionStorage.removeItem(draftKey);
      } catch {
        // ignore
      }
    }
    onOpenChange(next);
  }

  function submit(): void {
    if (!valid) return;
    onSubmit({
      reason_code: reasonCode,
      reason_text: trimmed,
      override_outcome: outcome as ReviewOutcome,
    });
    try {
      window.sessionStorage.removeItem(draftKey);
    } catch {
      // ignore
    }
  }

  return (
    <Modal
      open={open}
      onOpenChange={handleOpenChange}
      title="Override the recommendation"
      description="An override diverges from the system decision, so it must be explained."
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={() => handleOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            loading={submitting}
            disabled={!valid}
            onClick={submit}
          >
            Submit override
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="flex items-center justify-between rounded bg-sunken px-3 py-2 text-sm">
          <span>
            <span className="text-muted">System recommends </span>
            <span className="font-medium text-ink">{recommendation}</span>
          </span>
          <span aria-hidden="true" className="text-muted">→</span>
          <span>
            <span className="text-muted">Your outcome </span>
            <span className="font-medium text-ink">{outcome || "—"}</span>
          </span>
        </div>

        <label className="block space-y-1 text-sm">
          <span className="text-muted">Outcome</span>
          <Select value={outcome} onChange={(e) => setOutcome(e.target.value as ReviewOutcome | "")}>
            <option value="">Choose an outcome…</option>
            {OUTCOMES.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </Select>
        </label>

        <label className="block space-y-1 text-sm">
          <span className="text-muted">Reason code</span>
          <Select value={reasonCode} onChange={(e) => setReasonCode(e.target.value)}>
            <option value="">Choose a reason…</option>
            {REASON_CODES.map((r) => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </Select>
        </label>

        <label className="block space-y-1 text-sm">
          <span className="text-muted">Reason (required)</span>
          <textarea
            value={reasonText}
            onChange={(e) => updateReasonText(e.target.value)}
            rows={4}
            className="w-full rounded border border-border-strong bg-surface p-2 text-body text-ink"
            placeholder="Explain why you are diverging from the recommendation…"
          />
          <span
            className={cn(
              "block text-xs",
              trimmed.length >= MIN_REASON_LENGTH ? "text-muted" : "text-caution",
            )}
          >
            {trimmed.length}/{MIN_REASON_LENGTH} characters
          </span>
        </label>

        {errorMessage ? (
          <div
            role="alert"
            className="flex items-start gap-2 rounded border border-negative bg-negative-subtle p-3 text-sm text-negative"
          >
            <span className="mt-0.5 shrink-0">
              <Icon name="shield" size={16} />
            </span>
            <div>
              <p className="font-medium">Authority required</p>
              <p className="mt-0.5 text-negative/90">{errorMessage}</p>
            </div>
          </div>
        ) : null}
      </div>
    </Modal>
  );
}
