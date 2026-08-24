# Aperture — Judge Q&A cheat-sheet (say this, not that)

One page, verified against the code. The through-line: **"Model estimates, policy decides —
and nothing AI ever decides anything."**

---

## The 20-second pitch

> Nothing AI *decides* anything. Risk, affordability, coverage and fraud checks are pure
> deterministic math, and a transparent 9-gate policy engine makes the call. The live risk
> model is a *published scorecard* — every weight is visible and testable — deliberately
> labelled **uncalibrated** because we don't yet have repayment outcomes for new-to-credit
> applicants to train on; once the pilot generates them, v2 gets trained and calibrated. We
> did train an XGBoost, but only as a *benchmark* on public data. The only place an LLM
> appears is to *phrase* things for humans — the applicant's decline letter and an
> "explain this decision" helper — grounded in real facts, with a deterministic fallback.
> It's OpenAI with a Gemini fallback today, and the provider is swappable.

---

## Which models? (the #1 question)

Two risk models live in the registry (`backend/app/services/risk/registry.py`):

| | What it is | Role | Trained on |
|---|---|---|---|
| **Model B — cash-flow scorecard** | Transparent additive-logistic **points model**, 11 weighted features, exact closed-form contributions, always **UNCALIBRATED** | **LIVE decider** | Expert-set weights (no labels to fit yet) |
| **Model A — XGBoost** | Gradient-boosted trees, isotonic-calibrated, TreeSHAP attribution | **Benchmark only** — comparison/ranking, does **not** decide | Public **UCI "Default of Credit Card Clients"** (30k rows) |

- **Do say:** "The model that decides is a transparent scorecard. We also trained an XGBoost
  as a benchmark on public data — but it doesn't drive live decisions, because training on a
  different population would import their bias."
- **Don't say:** "We didn't use ML" (you did — XGBoost) **or** "XGBoost decides" (it doesn't).
  Both are wrong; the precise version above is right.

---

## Is it "real ML"? Why a hand-weighted scorecard?

- You **can't** train a supervised model without repayment labels, and for **new-to-credit /
  thin-file** applicants those outcomes **don't exist yet**.
- Training on a proxy population just borrows its bias.
- That's exactly why the scorecard is honestly stamped **UNCALIBRATED** — it *ranks*, it
  doesn't claim a true probability (a bathroom scale that tells you "heavier than last week"
  but not a trustworthy exact kg).
- **After the pilot** produces real repayment outcomes → **v2 is trained and calibrated on them.**
- Line: *"Refusing to fake confidence we haven't earned is the sophisticated move, not a gap."*

---

## What decides? (all deterministic — no AI)

Every gate is pure math (`backend/app/services/policy/engine.py` — no LLM, no network):

- **Risk** = the scorecard's closed-form points.
- **Affordability** = debt-service-ratio math (income − obligations − new EMI vs a 0.5 ceiling).
- **Coverage** = weighted sum of six evidence components.
- **Manipulation** = deterministic detectors **D1–D8**.
- **Decision** = a pure **9-gate** policy engine.

**Do say:** "Model estimates, policy decides." **No LLM ever touches an outcome.**

---

## Where does the LLM appear? (text only, never decisioning)

The LLM layer is **provider-agnostic** (Bedrock / OpenAI / Gemini all behind one interface).
Currently wired: **OpenAI primary → Gemini fallback → deterministic template.** It is used in
exactly three places, all "typed facts in → validated text out":

1. **Applicant notices** — decline / recourse letters (English + Hindi).
2. **"Explain this decision"** — the case-file assistant.
3. **"Ask the codebase"** — the architecture Q&A assistant.

- **Do say:** "A provider-agnostic LLM layer — currently OpenAI with a Gemini fallback, and
  Bedrock is a drop-in option — used only to *phrase* explanations for humans."
- **Don't say:** "AWS Bedrock runs the LLM." ⚠️ Bedrock is *supported* but **not active** —
  the live config is OpenAI + Gemini. Either say it the way above, or actually set
  `LLM_PROVIDER=bedrock` before the demo.

---

## What is OpenAI used for on the backend?

Text generation only, never decisioning: (1) applicant notices, (2) the "Explain this
decision" assistant, (3) the "Ask the codebase" assistant. Each has a deterministic fallback,
so a provider outage never breaks the product — it just drops to a grounded summary.

---

## "Is Gemini the embeddings that decode transactions?" — clarify before you say it

Three things to keep straight:

- **Embeddings ≠ deciding.** They only *classify/label* transactions — matching a narration to
  a merchant category by semantic similarity (`classification/service.py`, `VECTOR_KNN`,
  0.82 similarity floor).
- **Embeddings are a *fallback*, not the primary decoder.** Transactions are classified **first
  by deterministic keyword rules**; the embedding similarity only catches what rules miss.
- **On the demo box, embeddings are OFF** (`EMBEDDING_PROVIDER=noop`; the prod default is a
  *local* sentence-transformers model, not Gemini). Gemini embeddings (`gemini-embedding-001`)
  are a *supported option* (`EMBEDDING_PROVIDER=gemini` + `ALLOW_EXTERNAL_EMBEDDINGS=true`).
- **Gemini's live role today is the LLM fallback**, not the transaction decoder.

**Do say:** "Transaction decoding is deterministic keyword rules, with an embedding-similarity
fallback for the long tail. Embeddings can run locally or via Gemini — but they only label
transactions, they never decide."

---

## Quick "don't say → say" table

| ❌ Don't say | ✅ Say |
|---|---|
| "We didn't use any ML." | "The live decider is a transparent scorecard; XGBoost is a benchmark on public data." |
| "XGBoost decides the risk." | "XGBoost is a benchmark only; the scorecard decides, the policy engine makes the call." |
| "AWS Bedrock runs our LLM." | "Provider-agnostic LLM — OpenAI primary, Gemini fallback, Bedrock is a drop-in." |
| "Gemini reads the transactions." | "Deterministic rules classify transactions; embeddings (local or Gemini) are a fallback and only label, never decide." |
| "The AI approves/declines." | "AI decides nothing. A deterministic 9-gate policy engine decides; the LLM only phrases explanations." |
| "The score is a real default probability." | "It's an uncalibrated *ranking* — honest until a pilot gives us outcomes to calibrate v2." |
