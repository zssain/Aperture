import { useState } from "react";

import { Skeleton } from "../../components/ui/Skeleton";
import { cn } from "../../lib/cn";
import { useNoticePreview } from "./useReview";

const LANGUAGES: ReadonlyArray<{ value: string; label: string }> = [
  { value: "en", label: "English" },
  { value: "hi", label: "हिन्दी" },
];

/** The applicant's exact notice text, with a language switcher. Shows precisely what will be
 * sent — the same template_params rendered in each language. */
export function NoticePreview({
  decisionId,
  kind = "recourse",
}: {
  decisionId: string;
  kind?: "decision" | "recourse";
}) {
  const [language, setLanguage] = useState("en");
  const query = useNoticePreview(decisionId, kind, language);

  return (
    <section aria-label="Notice preview" className="space-y-2 rounded border border-border p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-ink">Applicant notice</h3>
        <div role="group" aria-label="Language" className="flex gap-1">
          {LANGUAGES.map((lang) => (
            <button
              key={lang.value}
              type="button"
              aria-pressed={language === lang.value}
              onClick={() => setLanguage(lang.value)}
              className={cn(
                "rounded px-2 py-1 text-xs",
                language === lang.value ? "bg-sunken text-ink" : "text-muted hover:text-ink",
              )}
            >
              {lang.label}
            </button>
          ))}
        </div>
      </div>
      {query.isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : query.isError ? (
        <p className="text-sm text-negative">Could not render the notice.</p>
      ) : query.data ? (
        <div>
          <p className="font-medium text-ink">{query.data.subject}</p>
          <p className="mt-1 whitespace-pre-wrap text-sm text-muted">{query.data.body}</p>
        </div>
      ) : null}
    </section>
  );
}
