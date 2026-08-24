import { useState } from "react";

import { Icon } from "../../components/ui/Icon";
import { Input } from "../../components/ui/Input";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { SOURCE_NOTE, useAskArchitecture } from "./useAssistant";

const SUGGESTIONS = [
  "Where is the risk model and how are contributions computed?",
  "How does the policy engine decide?",
  "Where does the LLM touch the product?",
  "How is the account aggregator wired in?",
  "Where is tenant isolation enforced?",
];

/** "Under the hood" architecture guide. Answers "where in the repo is X?" grounded in a
 * curated, hand-verified map of REAL file paths — the model may only synthesise over the
 * candidate topics it is given, and every cited path is resolved server-side (no invented
 * files). Great for a hackathon judge walking the codebase. */
export function ArchitectureAssistant() {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const ask = useAskArchitecture();
  const result = ask.data;

  function submit(q: string): void {
    const clean = q.trim();
    if (!clean || ask.isPending) return;
    setQuestion(clean);
    ask.mutate(clean);
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Ask about the architecture"
        className="fixed bottom-5 right-5 z-30 inline-flex items-center gap-2 rounded-pill border border-accent bg-accent px-4 py-2.5 text-sm font-medium text-surface shadow-modal transition-opacity duration-fast hover:opacity-90"
      >
        <Icon name="sparkle" size={18} />
        <span className="hidden sm:inline">Ask the codebase</span>
      </button>

      <Modal
        open={open}
        onOpenChange={setOpen}
        size="lg"
        title="Ask the codebase"
        description="Grounded architecture guide — real file paths only, never invented. Read-only."
      >
        <div className="space-y-4">
          <form
            className="flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              submit(question);
            }}
          >
            <Input
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="e.g. Where is the fraud detection code?"
              maxLength={500}
              aria-label="Ask about the architecture"
              autoFocus
            />
            <Button type="submit" icon="sparkle" loading={ask.isPending} disabled={!question.trim()}>
              Ask
            </Button>
          </form>

          <div className="flex flex-wrap gap-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => submit(s)}
                disabled={ask.isPending}
                className="rounded-pill border border-border-strong bg-surface px-3 py-1 text-xs text-ink transition-colors duration-fast hover:bg-sunken disabled:opacity-50"
              >
                {s}
              </button>
            ))}
          </div>

          {ask.isError ? (
            <p role="alert" className="text-sm text-negative">
              Could not answer: {ask.error.message}
            </p>
          ) : null}

          {result ? (
            <div className="space-y-3 rounded border border-border bg-sunken p-3">
              <p className="whitespace-pre-line text-body text-ink">{result.answer}</p>

              {result.citations.length > 0 ? (
                <div className="space-y-2">
                  <p className="eyebrow">Files</p>
                  {result.citations.map((c, index) => (
                    <div key={index} className="space-y-1">
                      <p className="text-sm font-medium text-ink">{c.title}</p>
                      <ul className="space-y-0.5">
                        {c.paths.map((path) => (
                          <li key={path}>
                            <code className="rounded bg-surface px-1.5 py-0.5 font-mono text-xs text-accent">
                              {path}
                            </code>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              ) : null}

              <p className="flex items-center gap-1.5 text-xs text-muted">
                <Icon name={result.used_llm ? "sparkle" : "shield"} size={13} />
                {result.used_llm ? SOURCE_NOTE.llm : SOURCE_NOTE.deterministic}
              </p>
            </div>
          ) : null}
        </div>
      </Modal>
    </>
  );
}
