import { useState } from "react";

import { Button } from "../../../components/ui/Button";
import { NoticePreview } from "../NoticePreview";
import { RecourseOption } from "../RecourseOption";
import { useSendRecourse } from "../useReview";
import type { CaseData } from "../useCase";

/** Recourse tab: up to three actionable option cards, the applicant notice preview with a
 * language switch, and Send evidence request as the primary action. No viable recourse is stated
 * explicitly, never softened. */
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

  if (options.length === 0) {
    return (
      <p className="text-sm text-ink">
        There is no viable recourse for this case. No additional step from the applicant would
        change the outcome under the current policy.
      </p>
    );
  }

  return (
    <div data-testid="case-tab-body" className="space-y-6 case-wide:grid case-wide:grid-cols-2 case-wide:gap-8 case-wide:space-y-0">
      <div className="grid gap-3 md:grid-cols-2">
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

      <NoticePreview decisionId={decisionId} kind="recourse" />

      <div className="flex items-center gap-3">
        <Button
          variant="primary"
          size="sm"
          onClick={() => send.mutate({ language: "en" }, { onSuccess: () => setSent(true) })}
          disabled={send.isPending}
        >
          {send.isPending ? "Sending…" : "Send evidence request"}
        </Button>
        {sent ? <span role="status" className="text-sm text-positive">Evidence request sent.</span> : null}
        {send.isError ? (
          <span role="alert" className="text-sm text-negative">{send.error.message}</span>
        ) : null}
      </div>
    </div>
  );
}
