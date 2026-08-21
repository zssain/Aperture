/** Shared definitions surfaced by InfoHint. Keys are stable identifiers; the term
 * is the human label and the definition the plain-language explanation. Copy here is
 * descriptive only — it must never overstate the certainty of a measurement. */
export interface GlossaryEntry {
  term: string;
  definition: string;
}

export const GLOSSARY = {
  pd: {
    term: "Probability of default (PD)",
    definition:
      "The model's estimated likelihood that this applicant defaults over the loan term. It is one input to the decision, not the decision itself.",
  },
  uncalibrated: {
    term: "Uncalibrated",
    definition:
      "The model has not been calibrated on enough comparable outcomes for this segment, so the exact probability is not yet reliable. Read it as directional, not precise.",
  },
  evidence_coverage: {
    term: "Evidence coverage",
    definition:
      "How complete the applicant's evidence file is — the share of expected sources and history that are present. It measures completeness of evidence, not creditworthiness.",
  },
  dsr: {
    term: "Debt service ratio (DSR)",
    definition:
      "Proposed repayments plus existing obligations as a share of available income. A lower ratio leaves more headroom.",
  },
  headroom: {
    term: "Headroom",
    definition:
      "Income left after essential expenses and existing obligations — the amount available to service a new repayment.",
  },
  bureau_only_counterfactual: {
    term: "Bureau-only counterfactual",
    definition:
      "What the recommendation would have been using bureau data alone, without the additional evidence gathered here. It shows how much the extra evidence changed the outcome.",
  },
  aa_verified: {
    term: "AA verified",
    definition:
      "Data retrieved directly from a financial institution through an account aggregator, cryptographically signed at source — the strongest evidence tier.",
  },
  verification_status: {
    term: "Verification status",
    definition:
      "Whether manipulation checks ran and what they found. 'Could not run' is not the same as 'clear'.",
  },
  policy_version: {
    term: "Policy version",
    definition:
      "The exact version of the policy rule set that produced this decision. Held in the audit trail so the decision can be replayed deterministically.",
  },
  recourse: {
    term: "Recourse",
    definition:
      "The concrete steps or additional evidence that could change the outcome, and any alternative pathway the policy allows.",
  },
} as const satisfies Record<string, GlossaryEntry>;

export type GlossaryKey = keyof typeof GLOSSARY;
