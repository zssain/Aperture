import { Link } from "react-router-dom";

import { Icon, type IconName } from "../../components/ui/Icon";
import { cn } from "../../lib/cn";

/**
 * Public marketing homepage at `/`. Static, provider-free, keyboard-accessible.
 * Every number here is true to the architecture doc (4 assessments, 8 detectors,
 * 9 policy gates, 11-feature scorecard) — the product's whole point is not inventing
 * numbers, so neither does its homepage.
 */

const ctaPrimary =
  "inline-flex h-10 items-center justify-center gap-2 rounded border border-brand bg-brand px-5 text-body font-medium text-white transition-opacity duration-fast hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-nav";
const ctaGhost =
  "inline-flex h-10 items-center justify-center gap-2 rounded border border-nav-border bg-transparent px-5 text-body font-medium text-nav-fg transition-colors duration-fast hover:bg-nav-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-nav";

interface Step {
  icon: IconName;
  title: string;
  body: string;
}

const STEPS: Step[] = [
  {
    icon: "shield",
    title: "1 · Consent",
    body: "Nothing is read without an active, scoped consent — Account Aggregator-aligned and cryptographically recorded.",
  },
  {
    icon: "bank",
    title: "2 · Evidence",
    body: "Consented bank, UPI, utility and telecom history becomes an append-only, immutable evidence ledger.",
  },
  {
    icon: "document",
    title: "3 · Four assessments",
    body: "Risk, affordability, coverage and manipulation run independently over one point-in-time snapshot.",
  },
  {
    icon: "check",
    title: "4 · Policy decides",
    body: "A single versioned engine — nothing else — turns the four signals into a decision through a 9-gate ladder.",
  },
  {
    icon: "arrow-right",
    title: "5 · Recourse",
    body: "Every non-approval gets the cheapest verified change that would flip it to yes — proven, not promised.",
  },
];

interface Differentiator {
  icon: IconName;
  title: string;
  body: string;
}

const DIFFERENTIATORS: Differentiator[] = [
  {
    icon: "replay",
    title: "Provable decisions",
    body: "Any past decision replays byte-for-byte from its stored snapshot — identical action, terms and hashes, forever. An auditor can verify it in one click.",
  },
  {
    icon: "arrow-right",
    title: "Recourse to yes",
    body: "For every decline or referral, a search finds the cheapest verified path — connect a source, extend history, adjust amount — re-running the real policy to prove each option.",
  },
  {
    icon: "shield",
    title: "Eight fraud detectors",
    body: "Independent checks (D1–D8) for circular flows, pre-application bursts, edited balances, doctored PDFs and fraud rings — never reading the risk score, so their independence is real.",
  },
  {
    icon: "info",
    title: "Honest by construction",
    body: "The production scorecard is uncalibrated, so it is labelled UNCALIBRATED everywhere — in the database, the API type and the UI. Never dressed up as a trustworthy probability.",
  },
  {
    icon: "bank",
    title: "Consent-first",
    body: "Consent gates everything and its exact terms are hashed. Revoke it and future collection stops immediately, while the audit record of past decisions remains intact.",
  },
  {
    icon: "audit",
    title: "Tamper-evident ledger",
    body: "Every action appends to a per-tenant, hash-chained audit ledger. A single broken link is detectable, and decisions are never mutated or purged.",
  },
];

const INVARIANTS: string[] = [
  "Missing data stays missing. A null is a null with a reason — never quietly turned into a zero.",
  "The model estimates risk; only the policy engine decides. No model output is ever an action.",
  "If a required signal is unavailable, the decision fails to a human — it does not guess to stay alive.",
  "Every number on screen is traceable to the exact events, transformation and version behind it.",
  "An uncalibrated probability is labelled uncalibrated wherever it appears.",
];

function SectionHeading({ eyebrow, title, lead }: { eyebrow: string; title: string; lead?: string }) {
  return (
    <div className="mx-auto max-w-2xl text-center">
      <p className="eyebrow text-accent">{eyebrow}</p>
      <h2 className="mt-3 text-title font-semibold text-ink">{title}</h2>
      {lead ? <p className="mt-3 text-body text-muted">{lead}</p> : null}
    </div>
  );
}

export function HomePage() {
  return (
    <div className="min-h-screen bg-surface">
      {/* Header */}
      <header className="border-b border-nav-border bg-nav">
        <nav
          aria-label="Primary"
          className="mx-auto flex h-16 max-w-content items-center justify-between px-4 sm:px-6"
        >
          <img src="/brand/aperture-logo-light.svg" alt="Aperture" className="h-7 w-auto" width="158" height="36" />
          <div className="flex items-center gap-2">
            <a href="#how" className="hidden rounded px-3 py-2 text-sm font-medium text-nav-muted transition-colors duration-fast hover:text-nav-fg sm:inline-block">
              How it works
            </a>
            <Link
              to="/signin"
              className="inline-flex h-9 items-center rounded border border-brand bg-brand px-4 text-sm font-medium text-white transition-opacity duration-fast hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-nav"
            >
              Sign in
            </Link>
          </div>
        </nav>
      </header>

      <main>
        {/* Hero */}
        <section aria-labelledby="hero-heading" className="relative overflow-hidden bg-nav">
          <span
            aria-hidden="true"
            className="pointer-events-none absolute -right-32 -top-32 h-[28rem] w-[28rem] animate-glow rounded-pill"
            style={{ background: "radial-gradient(closest-side, rgba(16,158,119,0.28), rgba(16,158,119,0) 70%)" }}
          />
          <span
            aria-hidden="true"
            className="pointer-events-none absolute -bottom-40 left-1/4 h-[26rem] w-[26rem] animate-glow rounded-pill"
            style={{ animationDelay: "2s", background: "radial-gradient(closest-side, rgba(30,75,143,0.30), rgba(30,75,143,0) 70%)" }}
          />
          <div className="relative mx-auto max-w-content px-4 py-20 sm:px-6 sm:py-28">
            <div className="mx-auto max-w-3xl text-center">
              <p className="animate-rise eyebrow text-brand">Credit decisioning for thin-file applicants</p>
              <h1
                id="hero-heading"
                className="animate-rise mt-5 font-serif text-hero font-medium text-nav-fg"
                style={{ animationDelay: "120ms" }}
              >
                Credit decisions for the people credit bureaus can&rsquo;t see.
              </h1>
              <p
                className="animate-rise mx-auto mt-6 max-w-xl text-body leading-relaxed text-nav-muted"
                style={{ animationDelay: "220ms" }}
              >
                Aperture underwrites new-to-credit and thin-file borrowers from consented financial
                behaviour — not a bureau score — and makes every decision explainable, reproducible
                and honest about what it doesn&rsquo;t know.
              </p>
              <div
                className="animate-rise mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row"
                style={{ animationDelay: "320ms" }}
              >
                <Link to="/signin" className={ctaPrimary}>
                  Sign in
                  <Icon name="arrow-right" size={18} />
                </Link>
                <a href="#how" className={ctaGhost}>
                  See how it works
                </a>
              </div>
            </div>
          </div>
        </section>

        {/* The problem */}
        <section aria-labelledby="problem-heading" className="border-b border-border bg-surface">
          <div className="mx-auto max-w-content px-4 py-20 sm:px-6">
            <SectionHeading
              eyebrow="The problem"
              title="Billions of people are invisible to credit — and declined by default."
              lead="A bureau returns “no score,” so the lender says no. Yet those same people have rich, honest financial lives: salary or gig income landing every month, rent paid on time, years of cleared utility and phone bills."
            />
            <div className="mx-auto mt-12 grid max-w-4xl gap-4 sm:grid-cols-3">
              {[
                { stat: "No score", label: "What a bureau returns for a thin-file applicant." },
                { stat: "Declined", label: "The default answer when there is nothing to score." },
                { stat: "Consented behaviour", label: "The evidence Aperture reads instead — with permission." },
              ].map((item) => (
                <div key={item.stat} className="rounded border border-border bg-sunken p-6 text-center">
                  <p className="text-heading font-semibold text-ink">{item.stat}</p>
                  <p className="mt-2 text-sm text-muted">{item.label}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* How it works */}
        <section id="how" aria-labelledby="how-heading" className="scroll-mt-16 border-b border-border bg-sunken">
          <div className="mx-auto max-w-content px-4 py-20 sm:px-6">
            <SectionHeading
              eyebrow="How it works"
              title="Consent to decision, with recourse at the end."
              lead="One transactional pipeline, five honest steps. The risk model estimates; only the policy engine decides."
            />
            <ol className="mx-auto mt-12 grid max-w-5xl gap-4 md:grid-cols-3 lg:grid-cols-5">
              {STEPS.map((step) => (
                <li key={step.title} className="flex flex-col rounded border border-border bg-surface p-5">
                  <span className="flex h-9 w-9 items-center justify-center rounded bg-accent-subtle text-accent">
                    <Icon name={step.icon} size={18} />
                  </span>
                  <h3 className="mt-4 text-body font-semibold text-ink">{step.title}</h3>
                  <p className="mt-2 text-sm text-muted">{step.body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* Differentiators */}
        <section aria-labelledby="diff-heading" className="border-b border-border bg-surface">
          <div className="mx-auto max-w-content px-4 py-20 sm:px-6">
            <SectionHeading
              eyebrow="What makes it different"
              title="Built for trust, not just approval rates."
            />
            <div className="mx-auto mt-12 grid max-w-5xl gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {DIFFERENTIATORS.map((card) => (
                <div key={card.title} className="flex flex-col rounded border border-border bg-surface p-6">
                  <span className="flex h-10 w-10 items-center justify-center rounded bg-accent-subtle text-accent">
                    <Icon name={card.icon} size={20} />
                  </span>
                  <h3 className="mt-4 text-heading font-semibold text-ink">{card.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted">{card.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Honesty / invariants — the brand */}
        <section aria-labelledby="honesty-heading" className="relative overflow-hidden bg-nav">
          <span
            aria-hidden="true"
            className="pointer-events-none absolute -left-24 top-1/2 h-80 w-80 -translate-y-1/2 animate-glow rounded-pill"
            style={{ background: "radial-gradient(closest-side, rgba(16,158,119,0.22), rgba(16,158,119,0) 70%)" }}
          />
          <div className="relative mx-auto max-w-content px-4 py-20 sm:px-6">
            <div className="mx-auto max-w-3xl text-center">
              <p className="eyebrow text-brand">Our promise</p>
              <h2 id="honesty-heading" className="mt-3 font-serif text-title font-medium text-nav-fg">
                We never invent a number. When we don&rsquo;t know, we say so.
              </h2>
              <p className="mt-4 text-body text-nav-muted">
                These are enforced rules in the codebase, not aspirations — treated as defects when
                broken.
              </p>
            </div>
            <ul className="mx-auto mt-12 grid max-w-4xl gap-3 sm:grid-cols-2">
              {INVARIANTS.map((line) => (
                <li key={line} className="flex gap-3 rounded border border-nav-border bg-nav-raised p-4">
                  <span aria-hidden="true" className="mt-0.5 shrink-0 text-brand">
                    <Icon name="check" size={18} />
                  </span>
                  <span className="text-sm leading-relaxed text-nav-fg">{line}</span>
                </li>
              ))}
            </ul>
            <div className="mt-12 text-center">
              <Link to="/signin" className={ctaPrimary}>
                Enter the workspace
                <Icon name="arrow-right" size={18} />
              </Link>
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-border bg-sunken">
        <div className="mx-auto flex max-w-content flex-col gap-4 px-4 py-10 sm:px-6 md:flex-row md:items-center md:justify-between">
          <div>
            <img src="/brand/aperture-logo.svg" alt="Aperture" className="h-6 w-auto" width="135" height="31" />
            <p className="mt-2 max-w-md text-sm text-muted">
              A hackathon build: a deterministic, auditable credit-decisioning system for thin-file
              borrowers.
            </p>
          </div>
          <div className="flex flex-col gap-2 text-sm text-muted md:items-end">
            <p className={cn("font-mono text-xs")}>
              FastAPI · SQLAlchemy · Postgres 16 + pgvector · React · TypeScript · Vite
            </p>
            <a
              href="https://github.com"
              className="inline-flex items-center gap-1.5 rounded font-medium text-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              target="_blank"
              rel="noreferrer noopener"
            >
              View the source
              <Icon name="external" size={14} />
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
