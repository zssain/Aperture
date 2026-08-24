import { useState } from "react";

import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Chip } from "../../components/ui/Chip";
import { Icon } from "../../components/ui/Icon";
import { Input } from "../../components/ui/Input";
import { SOURCE_NOTE, useExplainDecision } from "./useAssistant";

const SUGGESTIONS = [
  "Why was this decided the way it was?",
  "What were the biggest risk factors?",
  "What would change the outcome?",
];

/** "Explain this decision" — a grounded assistant on the case file. It answers ONLY over
 * the decision's real facts (fired rules, exact risk contributions, affordability, coverage,
 * manipulation findings) and shows clickable citations back to each source tab. It is
 * explanatory only: it never made, and cannot change, the decision. */
export function ExplainDecisionPanel({
  applicationId,
  onCiteTab,
}: {
  applicationId: string;
  onCiteTab?: (tab: string) => void;
}) {
  const [question, setQuestion] = useState("");
  const explain = useExplainDecision(applicationId);
  const result = explain.data;

  function ask(q: string): void {
    const clean = q.trim();
    if (!clean || explain.isPending) return;
    setQuestion(clean);
    explain.mutate(clean);
  }

  return (
    <section
      aria-label="Explain this decision"
      className="space-y-3 rounded border border-accent/30 bg-accent-subtle/40 p-4"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <Icon name="sparkle" size={18} className="text-accent" />
          <h3 className="text-body font-semibold text-ink">Explain this decision</h3>
        </div>
        <Badge tone="muted">Read-only · grounded</Badge>
      </div>
      <p className="text-sm text-muted">
        Ask about this case. Answers are built only from the real facts on file — the fired
        rules, exact risk contributions, affordability and coverage — with citations you can open.
        This is explanatory: it never changes a decision.
      </p>

      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          ask(question);
        }}
      >
        <Input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="e.g. Why was this declined, and what would flip it?"
          maxLength={500}
          aria-label="Ask about this decision"
        />
        <Button type="submit" icon="sparkle" loading={explain.isPending} disabled={!question.trim()}>
          Explain
        </Button>
      </form>

      <div className="flex flex-wrap gap-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => ask(s)}
            disabled={explain.isPending}
            className="rounded-pill border border-border-strong bg-surface px-3 py-1 text-xs text-ink transition-colors duration-fast hover:bg-sunken disabled:opacity-50"
          >
            {s}
          </button>
        ))}
      </div>

      {explain.isError ? (
        <p role="alert" className="text-sm text-negative">
          Could not build an explanation: {explain.error.message}
        </p>
      ) : null}

      {result ? (
        <div className="space-y-3 rounded border border-border bg-surface p-3">
          <p className="whitespace-pre-line text-body text-ink">{result.answer}</p>

          {result.citations.length > 0 ? (
            <div className="space-y-1.5">
              <p className="eyebrow">Grounded in</p>
              <ul className="space-y-1">
                {result.citations.map((c, index) => (
                  <li key={index} className="flex items-start gap-2 text-sm">
                    <Chip tone="accent" className="shrink-0">
                      {c.label}
                    </Chip>
                    <span className="flex-1 text-muted">{c.detail}</span>
                    {onCiteTab ? (
                      <button
                        type="button"
                        onClick={() => onCiteTab(c.tab)}
                        className="inline-flex shrink-0 items-center gap-1 text-xs text-accent hover:underline"
                      >
                        Open<Icon name="arrow-right" size={12} />
                      </button>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <p className="flex items-center gap-1.5 text-xs text-muted">
            <Icon name={result.used_llm ? "sparkle" : "shield"} size={13} />
            {result.used_llm ? SOURCE_NOTE.llm : SOURCE_NOTE.deterministic}
          </p>
        </div>
      ) : null}
    </section>
  );
}
