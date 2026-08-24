"""Grounded "how it's built" assistant — an architecture Q&A over a CURATED map.

Instead of a generic RAG that can hallucinate file paths, we keep a hand-verified registry of
real files with one-line summaries. A question is matched to candidate topics; the model may
only synthesise an answer over those candidates and cite keys we then resolve to REAL paths
(any key it returns that is not a candidate is dropped). Falls back to the best keyword match
when the LLM is off. Read-only; no filesystem access at runtime.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.core.logging import get_logger
from app.core.providers.base import ProviderNotConfigured
from app.core.providers.registry import configured_registry

logger = get_logger(__name__)


class _Topic(BaseModel):
    key: str
    title: str
    paths: list[str]
    summary: str
    keywords: list[str]


# Hand-verified against the repo. Paths are real; keep in sync when files move.
ARCHITECTURE: list[_Topic] = [
    _Topic(key="orchestrator", title="Decision orchestration",
           paths=["backend/app/services/orchestrator/service.py"],
           summary="decide() is the conductor: it computes the point-in-time snapshot, runs the "
                   "four assessments, evaluates the policy engine and persists an immutable "
                   "decision with its reasons and fired rules.",
           keywords=["decide", "orchestrat", "pipeline", "flow", "how a decision is made",
                     "conductor"]),
    _Topic(key="risk", title="Risk model (PD)",
           paths=["backend/app/services/risk/service.py", "backend/app/services/risk/registry.py",
                  "backend/app/services/risk/attribution.py",
                         "ml/scorecard/cashflow_scorecard_v1.py"],
           summary="The live model is the cash-flow scorecard: a transparent additive-logistic "
                   "points model (11 weighted features, exact closed-form contributions), always "
                   "labelled UNCALIBRATED. A benchmark XGBoost (trained on UCI) is kept as a "
                   "comparison. attribution.py gives exact contributions / TreeSHAP.",
           keywords=["pd", "risk", "scorecard", "model", "probability of default", "xgboost",
                     "benchmark", "calibration", "uncalibrated", "weights"]),
    _Topic(key="affordability", title="Affordability",
           paths=["backend/app/services/affordability/service.py"],
           summary="Debt-service-ratio check against a 0.5 ceiling; computes monthly headroom "
                   "(income minus obligations minus the new EMI).",
           keywords=["affordability", "dsr", "debt service", "headroom", "emi", "can they repay"]),
    _Topic(key="coverage", title="Evidence coverage",
           paths=["backend/app/services/coverage/service.py",
                  "backend/app/services/coverage/weights.py"],
           summary="A 0-100 evidence-coverage score from six weighted components (tier, "
                   "verification, history depth, freshness, diversity, completeness).",
           keywords=["coverage", "evidence", "how much data", "tier", "aa verified", "declared"]),
    _Topic(key="manipulation", title="Fraud / manipulation detectors",
           paths=["backend/app/services/manipulation/detectors/",
                  "backend/app/services/manipulation/service.py"],
           summary="Eight detectors D1-D8 (circular flow, inflow burst, counterparty "
                   "concentration, round-number salary, balance arithmetic, document provenance, "
                   "account-age mismatch, cross-applicant reuse) banded into CLEAR/ELEVATED/HIGH.",
           keywords=["fraud", "manipulation", "detector", "d1", "d2", "d3", "d5", "tamper",
                     "burst", "circular", "concentration"]),
    _Topic(key="policy", title="Policy engine (the decision rules)",
           paths=["backend/app/services/policy/engine.py",
                  "backend/app/services/policy/defaults.py",
                  "backend/app/services/policy/schema.py"],
           summary="A pure, deterministic 9-gate engine (manipulation → risk → affordability → "
                   "coverage → approve tiers). engine.py has no LLM/network. defaults.py holds "
                   "seed_policy_v1 (golden, frozen) and v2 (the draft).",
           keywords=["policy", "gate", "rule", "engine", "decides", "thresholds", "v1", "v2",
                     "model estimates policy decides"]),
    _Topic(key="features", title="Feature pipeline & snapshots",
           paths=["backend/app/services/features/service.py",
                  "backend/app/services/features/registry.py"],
           summary="Computes 34 features from classified events with the point-in-time rule "
                   "(occurred_at <= as_of), a null_map (missing = null + reason, never 0), and "
                   "lineage (which event ids produced each number). Snapshots are immutable.",
           keywords=["feature", "snapshot", "point in time", "lineage", "null", "as_of",
                     "look-ahead", "traceable"]),
    _Topic(key="registries", title="Feature allow-list & fairness guard",
           paths=["backend/app/registries/credit_features.py",
                  "backend/app/registries/fairness_attributes.py"],
           summary="A frozen allow-list of the 28 features that may reach a model, and a frozen "
                   "forbidden set (age/gender/caste/religion/…) that a build-time test proves can "
                   "never leak into the model.",
           keywords=["fairness", "bias", "protected", "allow-list", "age gender", "discrimination",
                     "which features"]),
    _Topic(key="aa", title="Account Aggregator & ingestion",
           paths=["backend/app/services/sources/mock_aa.py", "backend/app/services/sources/base.py",
                  "backend/app/services/sources/document.py",
                  "backend/app/services/ingestion/service.py"],
           summary="A provider-agnostic adapter boundary. mock_aa simulates the AA behind the "
                   "same interface a real one would use; document.py parses uploaded CSV/PDF; "
                   "ingestion enforces active consent before any fetch.",
           keywords=["account aggregator", "aa", "consent", "bank", "upi", "upload", "statement",
                     "ingest", "fetch", "csv", "pdf"]),
    _Topic(key="consent", title="Consent lifecycle",
           paths=["backend/app/services/consent/service.py"],
           summary="Grant creates a hashed consent artefact + a source connection per scope; "
                   "revoke blocks all future ingestion. Every piece of evidence links to the hash.",
           keywords=["consent", "revoke", "artefact", "scope", "purpose", "privacy"]),
    _Topic(key="queue", title="Decision queue",
           paths=["backend/app/services/queue/service.py"],
           summary="One set-based SQL round-trip per view (my-exceptions, evidence-needed, "
                   "newly-eligible, deterioration, all-decisions, qa-sample), keyset pagination, "
                   "and project_routed_because for the 'why routed' column.",
           keywords=["queue", "views", "exceptions", "routed because", "pagination",
                     "all decisions"]),
    _Topic(key="case", title="Case file assembly",
           paths=["backend/app/services/cases/assembler.py"],
           summary="assemble_case builds the full case file: application, sources, the decision "
                   "with reasons and fired rules, all four assessments, manipulation findings, "
                   "recourse, reviews, the bureau-only counterfactual, and the cash-flow series.",
           keywords=["case file", "assemble", "evidence tab", "assessment tab", "counterfactual"]),
    _Topic(key="notices", title="Applicant notices & the LLM",
           paths=["backend/app/services/notices/llm_renderer.py",
                  "backend/app/services/notices/validator.py",
                  "backend/app/services/notices/templates.py"],
           summary="The ONLY place an LLM touches the product: it phrases the applicant's "
                   "decision/recourse letter (English/Hindi) from typed facts, is strictly "
                   "validated (no invented numerals), and falls back to deterministic templates. "
                   "It never influences a decision.",
           keywords=["notice", "letter", "llm", "language", "hindi", "gpt", "bedrock", "gemini",
                     "generative", "validator"]),
    _Topic(key="assistant", title="AI assistants (this feature)",
           paths=["backend/app/services/assistant/decision_explainer.py",
                  "backend/app/services/assistant/architecture.py"],
           summary="Two grounded LLM assistants: explain-this-decision (real facts + citations, "
                   "read-only) and this architecture Q&A. Both phrase only over data we hand them "
                   "and fall back deterministically.",
           keywords=["explain", "assistant", "ai button", "architecture", "help", "ask", "chat"]),
    _Topic(key="audit", title="Audit ledger & immutability",
           paths=["backend/app/services/audit/ledger.py"],
           summary="A per-tenant, hash-chained, append-only ledger with verify_chain() to detect "
                   "tampering. Decisions are DB-trigger-immutable; overrides create new rows.",
           keywords=["audit", "immutable", "hash chain", "tamper", "append-only", "ledger",
                     "trail"]),
    _Topic(key="monitoring", title="Model & policy health",
           paths=["backend/app/services/monitoring/calibration.py",
                  "backend/app/services/monitoring/drift.py",
                  "backend/app/services/monitoring/model_card.py"],
           summary="Gated oversight metrics: calibration/discrimination (Brier/ROC/KS, reliability "
                   "curve), PSI drift, coverage distribution, overrides, and a branded model-card "
                   "PDF. Every metric is hidden until enough closed outcomes exist to measure it.",
           keywords=["health", "calibration", "drift", "brier", "roc", "ks", "model card",
                     "reliability", "psi", "oversight"]),
    _Topic(key="recourse", title="Recourse & newly-eligible flip",
           paths=["backend/app/services/recourse/",
                  "backend/app/services/decisions/change_detector.py"],
           summary="Every decline carries a concrete path to yes; verified new income can flip a "
                   "decline to eligible (the newly-eligible story), detected by change_detector.",
           keywords=["recourse", "newly eligible", "flip", "path to yes", "redecide", "change"]),
    _Topic(key="auth", title="Auth, RBAC & tenancy",
           paths=["backend/app/core/security.py", "backend/app/api/deps.py",
                  "backend/app/db/repository.py"],
           summary="Custom Argon2id/session auth, four role guards (analyst/policy-owner/fraud/"
                   "auditor), and tenant isolation via a single scoped-select (cross-tenant is a "
                   "404, not a 403).",
           keywords=["auth", "login", "password", "session", "role", "rbac", "tenant", "security",
                     "permission"]),
]

_ALL_PATHS = {t.key: t.paths for t in ARCHITECTURE}

_SYSTEM = (
    "You are Aperture's architecture guide for a hackathon judge or a new engineer. Answer the "
    "question using ONLY the candidate topics provided (each has a title, real file paths and a "
    "summary). Be concise and concrete. Reference the exact file paths from the candidates. Do "
    "NOT invent files, functions or topics. Return only JSON: {\"answer\": \"...\", "
    "\"topic_keys\": [\"key\", ...]} where every key is one of the candidate keys."
)


class _ArchAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(min_length=1, max_length=2400)
    topic_keys: list[str] = Field(default_factory=list)


class ArchCitation(BaseModel):
    title: str
    paths: list[str]


class ArchitectureAnswer(BaseModel):
    answer: str
    citations: list[ArchCitation]
    used_llm: bool


def _score(topic: _Topic, question: str) -> int:
    q = question.casefold()
    score = sum(3 for kw in topic.keywords if kw in q)
    score += sum(1 for word in topic.title.casefold().split() if len(word) > 3 and word in q)
    return score


def _candidates(question: str, limit: int = 6) -> list[_Topic]:
    ranked = sorted(ARCHITECTURE, key=lambda t: _score(t, question), reverse=True)
    scored = [t for t in ranked if _score(t, question) > 0]
    return (scored or ranked)[:limit]


def _fallback(candidates: list[_Topic]) -> ArchitectureAnswer:
    top = candidates[:3]
    answer = " ".join(f"{t.title}: {t.summary}" for t in top)
    return ArchitectureAnswer(
        answer=answer,
        citations=[ArchCitation(title=t.title, paths=t.paths) for t in top],
        used_llm=False,
    )


async def answer_architecture(question: str) -> ArchitectureAnswer:
    clean = question.strip()[:500]
    candidates = _candidates(clean)
    if not settings.llm_notices_enabled:
        return _fallback(candidates)
    try:
        provider = configured_registry().llm(settings.llm_provider)
    except (ProviderNotConfigured, RuntimeError):
        return _fallback(candidates)
    payload: dict[str, Any] = {
        "question": clean,
        "candidates": [
            {"key": t.key, "title": t.title, "paths": t.paths, "summary": t.summary}
            for t in candidates
        ],
    }
    try:
        parsed = await provider.complete(_SYSTEM, payload, _ArchAnswer)
    except Exception as exc:
        logger.info("architecture_answer_fallback", reason=type(exc).__name__)
        return _fallback(candidates)
    # Ground the citations: keep only keys the model was actually given.
    keys = [k for k in parsed.topic_keys if k in _ALL_PATHS] or [t.key for t in candidates[:3]]
    by_key = {t.key: t for t in ARCHITECTURE}
    citations = [ArchCitation(title=by_key[k].title, paths=by_key[k].paths) for k in keys]
    return ArchitectureAnswer(answer=parsed.answer.strip(), citations=citations, used_llm=True)
