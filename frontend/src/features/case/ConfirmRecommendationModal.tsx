import { Button } from "../../components/ui/Button";
import { DetailRow } from "../../components/ui/Card";
import { Chip } from "../../components/ui/Chip";
import { Modal } from "../../components/ui/Modal";
import { formatPaise } from "../../lib/format";
import type { CaseData } from "./useCase";

/**
 * Confirmation for accepting the system recommendation. A credit decision must not be
 * confirmable by accident, so this restates the applicant, amount, recommendation and
 * the key reasoning before Cancel / Confirm. It changes nothing about the backing
 * mutation or its safeguards — it only gates the click.
 */
export function ConfirmRecommendationModal({
  data,
  open,
  onOpenChange,
  onConfirm,
  submitting,
}: {
  data: CaseData;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
  submitting: boolean;
}) {
  const decision = data.decision;
  const applicant = data.applicant.display_name ?? data.applicant.external_ref;
  const amount = decision?.approved_limit_paise ?? data.application.requested_amount_paise;
  const reasons = decision?.reasons ?? [];

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title="Confirm recommendation"
      description="This records the decision on the case and returns you to the queue."
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            icon="check"
            loading={submitting}
            onClick={onConfirm}
          >
            Confirm decision
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="rounded border border-border">
          <div className="px-3">
            <DetailRow label="Applicant">{applicant}</DetailRow>
            <DetailRow label="Amount">
              {amount !== null ? formatPaise(amount) : "—"}
            </DetailRow>
            <DetailRow label="Recommendation">
              {decision ? (
                <Chip tone="neutral" className="font-mono">
                  {decision.outcome}
                </Chip>
              ) : (
                "—"
              )}
            </DetailRow>
          </div>
        </div>

        {reasons.length > 0 ? (
          <div>
            <p className="eyebrow mb-1">Key reasoning</p>
            <ul className="space-y-1 text-sm text-muted">
              {reasons.slice(0, 3).map((reason) => (
                <li key={reason.code}>{reason.message}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </Modal>
  );
}
