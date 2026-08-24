# Aperture — Code map (where everything lives)

For demos: a judge asks "show me X", you open the file and say the one-liner. Every path is
real and verified. **Killer move:** click **"Ask the codebase"** (bottom-right, any page) and
type "where is the risk model?" — it answers with real file paths, live. That feature is
[architecture.py](../backend/app/services/assistant/architecture.py).

If you only memorize three files:
[orchestrator/service.py](../backend/app/services/orchestrator/service.py) (the flow) →
[policy/engine.py](../backend/app/services/policy/engine.py) (the deterministic decider) →
[cashflow_scorecard_v1.py](../ml/scorecard/cashflow_scorecard_v1.py) (the transparent model).
They tell the whole "model estimates, policy decides" story.

---

## The decision flow — "how does a decision get made?"

- **The conductor** → [orchestrator/service.py](../backend/app/services/orchestrator/service.py)
  — `decide()`: computes the point-in-time snapshot, runs the four assessments, calls the
  policy engine, writes an immutable decision. *"This one function is the whole pipeline."*
- **The decider (deterministic)** → [policy/engine.py](../backend/app/services/policy/engine.py)
  — a pure 9-gate engine, no LLM, no network. Rules seed in
  [policy/defaults.py](../backend/app/services/policy/defaults.py) (`seed_policy_v1`, frozen).
  *"Model estimates, policy decides — this is 'policy'."*

## The models — the #1 question

- **Live risk model (scorecard)** → [ml/scorecard/cashflow_scorecard_v1.py](../ml/scorecard/cashflow_scorecard_v1.py)
  — transparent additive-logistic points model, every weight visible, always UNCALIBRATED.
- **Both models + which is live vs benchmark** → [risk/registry.py](../backend/app/services/risk/registry.py)
  — scorecard = **live decider**, XGBoost = **benchmark only** (trained on public UCI data).
- **Exact contributions / SHAP** → [risk/attribution.py](../backend/app/services/risk/attribution.py)
- **Risk scoring service** → [risk/service.py](../backend/app/services/risk/service.py)

## The four assessments

- **Affordability (DSR math)** → [affordability/service.py](../backend/app/services/affordability/service.py)
- **Coverage (0–100 evidence score)** → [coverage/service.py](../backend/app/services/coverage/service.py),
  weights in [coverage/weights.py](../backend/app/services/coverage/weights.py)
- **Fraud / manipulation (D1–D8)** → [manipulation/detectors/](../backend/app/services/manipulation/detectors/)
  + [manipulation/service.py](../backend/app/services/manipulation/service.py)

## Fairness — "you're not using protected attributes?"

- [registries/credit_features.py](../backend/app/registries/credit_features.py) (allow-list of the
  28 features that may reach a model) + [registries/fairness_attributes.py](../backend/app/registries/fairness_attributes.py)
  (frozen forbidden set: age/gender/caste/religion/…). *"A build-time test proves these can
  never reach the model."*

## Features — "no look-ahead / point-in-time?"

- [features/service.py](../backend/app/services/features/service.py) — 34 features, the
  point-in-time rule (`occurred_at <= as_of`), missing = null (never 0), full lineage.

## Account Aggregator + transactions

- **AA adapter boundary** → [sources/base.py](../backend/app/services/sources/base.py), mock in
  [sources/mock_aa.py](../backend/app/services/sources/mock_aa.py)
- **Ingestion (enforces active consent)** → [ingestion/service.py](../backend/app/services/ingestion/service.py)
- **Transaction classification (deterministic rules + embedding fallback)** →
  [classification/service.py](../backend/app/services/classification/service.py)
- **Consent lifecycle** → [consent/service.py](../backend/app/services/consent/service.py)

## The LLM — "where does AI touch it?"

- **Applicant notices** → [notices/llm_renderer.py](../backend/app/services/notices/llm_renderer.py)
  + strict [notices/validator.py](../backend/app/services/notices/validator.py)
- **Explain-this-decision assistant** → [assistant/decision_explainer.py](../backend/app/services/assistant/decision_explainer.py)
- **Ask-the-codebase assistant** → [assistant/architecture.py](../backend/app/services/assistant/architecture.py)
- **Provider layer + OpenAI→Gemini fallback** → [assistant/llm.py](../backend/app/services/assistant/llm.py),
  [core/providers/registry.py](../backend/app/core/providers/registry.py).
  *"The LLM only phrases text for humans; it never decides."*

## Trust — "prove it wasn't tampered with"

- **Hash-chained, append-only ledger** → [audit/ledger.py](../backend/app/services/audit/ledger.py)
  — `verify_chain()`. Decisions are DB-trigger immutable; overrides create new rows.

## Model & policy health (the Health page)

- [monitoring/calibration.py](../backend/app/services/monitoring/calibration.py),
  [monitoring/drift.py](../backend/app/services/monitoring/drift.py),
  [monitoring/model_card.py](../backend/app/services/monitoring/model_card.py) — Brier/ROC/KS,
  reliability curve, PSI drift, and the branded model-card PDF.

## Recourse — "path to yes" / newly-eligible flip

- [recourse/](../backend/app/services/recourse/) +
  [decisions/change_detector.py](../backend/app/services/decisions/change_detector.py)

## Auth / RBAC / tenancy

- [core/security.py](../backend/app/core/security.py) (Argon2id sessions),
  [api/deps.py](../backend/app/api/deps.py) (role guards),
  [db/repository.py](../backend/app/db/repository.py) (tenant isolation — cross-tenant is a
  404, not a 403).

---

## Frontend — "show the UI code"

- **Case file (the main screen)** → [CaseFilePage.tsx](../frontend/src/features/case/CaseFilePage.tsx)
  + [tabs/](../frontend/src/features/case/tabs/)
- **The decision queue** → [features/queue/](../frontend/src/features/queue/)
- **The two AI features** → [ExplainDecisionPanel.tsx](../frontend/src/features/assistant/ExplainDecisionPanel.tsx),
  [ArchitectureAssistant.tsx](../frontend/src/features/assistant/ArchitectureAssistant.tsx)
- **Model & policy health** → [features/health/](../frontend/src/features/health/)
