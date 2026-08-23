import * as RadixPopover from "@radix-ui/react-popover";

import { Icon } from "../../components/ui/Icon";

/** An "i" affordance next to the upload heading that explains, in a compact and
 * well-structured panel, what happens to a statement after it is uploaded — the
 * pipeline, the features it computes, and the honesty rules. Keyboard/touch reachable
 * (a real button), matching the app's existing InfoHint popover pattern. */

interface Step {
  n: number;
  title: string;
  body: string;
}

const STEPS: Step[] = [
  { n: 1, title: "Read & classify", body: "Every transaction is typed — salary, rent, EMI, utility, telecom or spend." },
  { n: 2, title: "Build features", body: "Point-in-time metrics are computed from your history (listed below)." },
  { n: 3, title: "Assess four ways", body: "Risk, affordability, coverage and fraud are scored independently." },
  { n: 4, title: "Policy decides", body: "One versioned engine turns those four into approve, refer or decline." },
  { n: 5, title: "Recourse", body: "If it isn't a yes, the cheapest verified path to one is worked out." },
];

interface Feature {
  term: string;
  meaning: string;
}

const FEATURES: Feature[] = [
  { term: "Income consistency", meaning: "how steady your monthly inflows are" },
  { term: "Debt-service ratio", meaning: "loan EMIs as a share of income (50% ceiling)" },
  { term: "Expense cover", meaning: "months of essentials your balance could cover" },
  { term: "Bill-payment streaks", meaning: "unbroken months of utility / telecom payments" },
  { term: "Evidence coverage", meaning: "how much we actually know, scored 0–100" },
];

export function UploadInfo() {
  return (
    <RadixPopover.Root>
      <RadixPopover.Trigger asChild>
        <button
          type="button"
          aria-label="How an uploaded statement is assessed"
          className="inline-flex h-5 w-5 items-center justify-center rounded-pill border border-border-strong text-muted transition-colors duration-fast hover:border-accent hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          <Icon name="info" size={13} />
        </button>
      </RadixPopover.Trigger>
      <RadixPopover.Portal>
        <RadixPopover.Content
          align="start"
          sideOffset={8}
          collisionPadding={12}
          className="z-50 w-[22rem] max-w-screen-safe animate-sheet-in overflow-y-auto rounded border border-border bg-surface shadow-drawer"
          style={{ maxHeight: "min(30rem, calc(100vh - 3rem))" }}
        >
          <div className="border-b border-border p-4">
            <p className="eyebrow text-accent">Behind the scenes</p>
            <p className="mt-1 text-heading font-semibold text-ink">
              How your statement becomes a decision
            </p>
          </div>

          <div className="p-4">
            <p className="eyebrow text-muted">The pipeline</p>
            <ol className="mt-2 space-y-2.5">
              {STEPS.map((step) => (
                <li key={step.n} className="flex gap-2.5">
                  <span
                    aria-hidden="true"
                    className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-pill bg-accent-subtle text-xs font-semibold text-accent"
                  >
                    {step.n}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-medium text-ink">{step.title}</span>
                    <span className="block text-sm text-muted">{step.body}</span>
                  </span>
                </li>
              ))}
            </ol>
          </div>

          <div className="border-t border-border p-4">
            <p className="eyebrow text-muted">What we compute</p>
            <dl className="mt-2 space-y-1.5">
              {FEATURES.map((feature) => (
                <div key={feature.term} className="flex flex-col sm:flex-row sm:gap-1.5">
                  <dt className="text-sm font-medium text-ink">{feature.term}</dt>
                  <dd className="text-sm text-muted sm:before:mr-1 sm:before:content-['—']">
                    {feature.meaning}
                  </dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="border-t border-border p-4">
            <div className="flex gap-2 rounded border border-border bg-sunken p-3">
              <span aria-hidden="true" className="mt-0.5 shrink-0 text-accent">
                <Icon name="shield" size={15} />
              </span>
              <p className="text-xs leading-relaxed text-muted">
                Uploaded statements are <span className="font-medium text-ink">declared
                documents</span> — lighter evidence weight than a bank-verified connection.
                Anything we can&rsquo;t observe is shown as &ldquo;—&rdquo; with a reason,
                never guessed.
              </p>
            </div>
          </div>
          <RadixPopover.Arrow className="fill-surface" />
        </RadixPopover.Content>
      </RadixPopover.Portal>
    </RadixPopover.Root>
  );
}
