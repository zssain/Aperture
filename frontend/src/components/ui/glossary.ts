/** Shared definitions surfaced by InfoHint. Keys are stable identifiers; the term is
 * the human label, `definition` the plain-language "what it is", `howCalculated` the
 * method in words, `formula` an exact (monospace) expression, and `note` an honest
 * caveat. Copy here is descriptive only — it must never overstate the certainty of a
 * measurement. Formulas mirror the production engines (scorecard, affordability,
 * coverage, manipulation); keep them in sync if a version changes. */
export interface GlossaryEntry {
  term: string;
  definition: string;
  howCalculated?: string;
  formula?: string;
  note?: string;
}

export const GLOSSARY = {
  pd: {
    term: "Probability of default (PD)",
    definition:
      "The model's estimated likelihood that this applicant defaults over the loan term. It is one input to the decision, not the decision itself — only the policy engine decides.",
    howCalculated:
      "A transparent additive scorecard over 11 cash-flow features. Each feature is scaled to a bounded range and multiplied by a published weight in log-odds; the weighted sum is passed through a logistic curve to a probability. Every feature's contribution is exact and shown in the breakdown below.",
    formula: "PD = 1 / (1 + e^−(intercept + Σ weightᵢ · featureᵢ)) ,  intercept = logit(0.15)",
    note: "Production scorecard is UNCALIBRATED — read it as directional, not an exact probability.",
  },
  uncalibrated: {
    term: "Uncalibrated",
    definition:
      "The model has not yet been calibrated against enough closed outcomes for this segment, so the exact probability is not verified.",
    howCalculated:
      "Calibration compares predicted probabilities to actual observed default rates once loans close. Until enough have closed, the score is left explicitly labelled rather than presented as a trustworthy percentage.",
    note: "Shown in grey with an UNCAL chip everywhere — never styled as a confident, calibrated number.",
  },
  evidence_coverage: {
    term: "Evidence coverage",
    definition:
      "How complete the applicant's evidence file is — the share of expected sources and history present. It measures completeness of evidence, not creditworthiness.",
    howCalculated:
      "A 0–100 weighted score over six components: source tier (20), verification (15), history depth (20), freshness (15), source diversity (15) and feature completeness (15).",
    formula: "score = Σ (weight_c × fraction_c) ,  0–100",
    note: "HIGH band needs a strong score AND more than one source type — a single source is capped at MEDIUM.",
  },
  dsr: {
    term: "Debt service ratio (DSR)",
    definition:
      "Proposed repayment plus existing obligations as a share of usable income. A lower ratio leaves more headroom.",
    howCalculated:
      "Income is the median monthly inflow (or the 25th percentile when income is irregular). The new EMI is computed on reducing-balance amortisation and added to existing obligations, then divided by income. A stress test re-checks it at −15% income and +20% obligations.",
    formula: "DSR = (existing EMI + new EMI) / net monthly income ,  ceiling = 0.50",
    note: "If income cannot be observed the result is INDETERMINATE, never a fabricated zero.",
  },
  headroom: {
    term: "Headroom",
    definition:
      "Income left after essential expenses and existing obligations — the amount available to service a new repayment.",
    formula: "headroom = net income − essential expenses − existing obligations",
  },
  bureau_only_counterfactual: {
    term: "Bureau-only counterfactual",
    definition:
      "What the recommendation would have been using bureau data alone, without the extra cash-flow evidence gathered here.",
    howCalculated:
      "The same policy engine is re-run with the bureau-derived signals only; the outcome is compared to the actual decision to show how much the extra evidence changed the result.",
  },
  aa_verified: {
    term: "AA verified",
    definition:
      "Data retrieved directly from a financial institution through an account aggregator, cryptographically signed at source — the strongest evidence tier.",
    note: "Tiers rank AA_VERIFIED > BANK_VERIFIED > DECLARED_DOCUMENT; an uploaded statement is a declared document and scores lower.",
  },
  verification_status: {
    term: "Verification (manipulation checks)",
    definition:
      "Whether the evidence itself looks honest. Eight independent detectors (D1–D8) look for signs a statement was edited or staged — separately from the credit score.",
    howCalculated:
      "Each detector returns OK, a finding with a severity, insufficient-data, or unavailable. Any HIGH finding sets the band to HIGH (fraud review); enough MEDIUMs set ELEVATED; otherwise CLEAR. Each finding links to the exact transactions that triggered it.",
    note: "A check that could not run is NOT the same as clear. Fraud logic never reads the risk score.",
  },
  policy_version: {
    term: "Policy version",
    definition:
      "The exact version of the policy rule set that produced this decision, held in the audit trail so the decision can be replayed deterministically.",
    howCalculated:
      "Exactly one policy version is live per tenant. The decision records which one ran, so replaying it against that version reproduces the identical outcome and hashes.",
  },
  bureau: {
    term: "Credit bureau signals",
    definition:
      "Signals from a traditional credit bureau file (score, active loans, recent delinquencies), when the applicant has one. Most thin-file applicants don't.",
    howCalculated:
      "Read directly from a consented bureau pull, stored as a bureau record. They add a verified source (raising coverage) and are shown for context.",
    note: "The production scorecard is cash-flow-only, so these do NOT change the PD — the point is to lend without needing them. Absent bureau data shows as '—', never 0.",
  },
  recourse: {
    term: "Recourse",
    definition:
      "The cheapest concrete change that would turn a non-approval into an approval — connecting a source, extending history, or adjusting the amount.",
    howCalculated:
      "The engine searches candidate changes in order of applicant effort and PROVES each by re-running the real policy engine with the change applied. Only options that genuinely flip the outcome are shown, easiest first.",
    note: "Guidance only, never a guarantee — and no internal thresholds are ever quoted to the applicant.",
  },
} as const satisfies Record<string, GlossaryEntry>;

export type GlossaryKey = keyof typeof GLOSSARY;
