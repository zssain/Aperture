import { useState } from "react";

import { Button } from "../../../components/ui/Button";
import { InfoHint } from "../../../components/ui/InfoHint";
import { NoticePreview } from "../NoticePreview";
import { RecourseOption } from "../RecourseOption";
import { useSendRecourse } from "../useReview";
import type { CaseData } from "../useCase";

/** Recourse tab: the current recommendation and why, up to three actionable option
 * cards, the applicant notice preview with a language switch, and Send evidence
 * request as the primary action. No viable recourse is stated explicitly, never
 * softened. */
export function RecourseTab({
  data,
  decisionId,
  onRerun,
}: {
  data: CaseData;
  decisionId: string;
  onRerun: () => void;
}) {
  const send = useSendRecourse(decisionId);
  const [sent, setSent] = useState(false);
  const options = data.recourse.slice(0, 3);
  const now = new Date();

  const outcome = data.decision?.outcome.replace(/_/g, " ") ?? "No decision";
  const topReason = data.decision?.reasons?.[0]?.message;

  return (
    <div data-testid="case-tab-body" className="space-y-6 case-wide:grid case-wide:grid-cols-2 case-wide:gap-8 case-wide:space-y-0">
      <section aria-label="Recourse" className="space-y-4 case-wide:col-span-2">
        <div className="rounded border border-border bg-surface p-4">
          <div className="flex items-center gap-2">
            <h3 className="eyebrow">Current recommendation</h3>
            <InfoHint term="recourse" />
          </div>
          <p className="mt-1 text-body font-medium text-ink">{outcome}</p>
          {topReason ? <p className="mt-1 text-sm text-muted">{topReason}</p> : null}
          <p className="mt-2 text-sm text-muted">
            Bureau-only counterfactual: {data.bureau_only.outcome.replace(/_/g, " ")} —{" "}
            {data.bureau_only.note}
          </p>
        </div>

        {options.length === 0 ? (
          <div className="rounded border border-border-strong bg-surface p-4">
            <p className="text-sm text-ink">
              There is no viable recourse for this case. No additional step from the
              applicant would change the outcome under the current policy.
            </p>
          </div>
        ) : (
          <>
            <p className="eyebrow">What could change the outcome</p>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {options.map((option) => (
                <RecourseOption
                  key={option.rank}
                  option={option}
                  policyVersion={data.decision?.policy_version ?? null}
                  now={now}
                  onRerun={onRerun}
                />
              ))}
            </div>
          </>
        )}
      </section>

      {/* The applicant notice is always previewable: the recourse (evidence-request) letter
          when there is a viable path, otherwise the decision letter itself. */}
      <NoticePreview decisionId={decisionId} kind={options.length > 0 ? "recourse" : "decision"} />

      {options.length > 0 ? (
        <>
          <section aria-label="Send request" className="space-y-3">
            <h3 className="eyebrow">Send to applicant</h3>
            <div className="flex flex-wrap items-center gap-3">
              <Button
                variant="primary"
                size="sm"
                icon="external"
                loading={send.isPending}
                onClick={() =>
                  send.mutate({ language: "en" }, { onSuccess: () => setSent(true) })
                }
              >
                Send evidence request
              </Button>
              {sent ? (
                <span role="status" className="text-sm text-positive">
                  Evidence request sent.
                </span>
              ) : null}
              {send.isError ? (
                <span role="alert" className="text-sm text-negative">
                  {send.error.message}
                </span>
              ) : null}
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}
