"""Grounded "explain this decision" assistant.

The differentiator: nothing here is invented. We assemble the decision's REAL facts — the
fired policy rules, the risk contributions (exact, closed-form), the affordability working,
coverage, manipulation findings and reasons — hand only those typed facts to the model, and
attach deterministic citations the analyst can click through to. The model may only *phrase*
the explanation; it can never change a decision (this is a read path) and it falls back to a
deterministic summary when the LLM is disabled or misbehaves. Same guardrail spine as notices.
"""

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.providers.base import ProviderNotConfigured
from app.core.providers.registry import configured_registry
from app.schemas.case import CaseOut
from app.services.cases.assembler import assemble_case

logger = get_logger(__name__)

_TAB = {
    "risk": "assessment",
    "affordability": "assessment",
    "coverage": "assessment",
    "verification": "verification",
    "decision": "decision",
    "recourse": "recourse",
}


class _Explanation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(min_length=1, max_length=2400)


class Citation(BaseModel):
    label: str
    detail: str
    tab: str  # which case tab backs this fact


class DecisionExplanation(BaseModel):
    answer: str
    citations: list[Citation]
    used_llm: bool


_SYSTEM = (
    "You are Aperture's decision explainer, helping a credit analyst understand ONE already-made "
    "decision. Rules: (1) Use ONLY the structured facts provided — never invent numbers, rules, "
    "features or outcomes. (2) You are read-only: never imply you made, could make, or could "
    "change the decision. (3) Be concise and specific; name the policy rule and the features that "
    "drove it, using the facts. (4) If the facts do not answer the question, say so plainly. "
    "Return only JSON: {\"answer\": \"...\"}."
)


def _fmt_paise(paise: int | None) -> str:
    return "—" if paise is None else f"₹{paise / 100:,.0f}"


def _top_contributions(payload: dict[str, Any], limit: int = 4) -> list[dict[str, Any]]:
    contribs = payload.get("contributions") or []
    present = [c for c in contribs if isinstance(c, dict) and c.get("present")]
    present.sort(key=lambda c: abs(float(c.get("contribution", 0.0))), reverse=True)
    return present[:limit]


def _build_facts(case: CaseOut) -> tuple[dict[str, Any], list[Citation]]:
    """Turn the assembled case into (compact facts for the model, clickable citations)."""
    decision = case.decision
    citations: list[Citation] = []
    facts: dict[str, Any] = {
        "requested_amount": _fmt_paise(case.application.requested_amount_paise),
        "requested_tenor_months": case.application.requested_tenor_months,
    }

    if decision is not None:
        decisive = next(
            (r for r in decision.fired_rules if isinstance(r, dict) and r.get("outcome")), None
        )
        facts["outcome"] = decision.outcome
        facts["decisive_rule"] = (
            f"{decisive.get('name')} ({decisive.get('outcome')})" if decisive else None
        )
        facts["approved_amount"] = _fmt_paise(decision.approved_limit_paise)
        facts["reasons"] = [r.message for r in decision.reasons][:5]
        citations.append(
            Citation(
                label="Decision",
                detail=f"{decision.outcome}"
                + (f" · rule: {decisive.get('name')}" if decisive else ""),
                tab="decision",
            )
        )
        for reason in decision.reasons[:4]:
            citations.append(Citation(label="Reason", detail=reason.message, tab="decision"))

    # Risk (PD + exact contributions)
    pd = case.chips.pd
    risk_assessment = case.assessments.get("RISK")
    risk_payload = risk_assessment.payload if risk_assessment is not None else {}
    facts["risk"] = {
        "pd": pd.value,
        "calibration": pd.status,
        "top_factors": [
            {
                "feature": c.get("feature"),
                "direction": c.get("direction"),
                "contribution": round(float(c.get("contribution", 0.0)), 4),
            }
            for c in _top_contributions(risk_payload)
        ],
    }
    if pd.value is not None:
        citations.append(
            Citation(
                label="Risk (PD)",
                detail=f"{pd.value:.3f} · {pd.status} (uncalibrated ranking, not a literal rate)",
                tab="assessment",
            )
        )
    for factor in facts["risk"]["top_factors"]:
        citations.append(
            Citation(
                label="Risk factor",
                detail=f"{factor['feature']} ({factor['direction']}, {factor['contribution']:+})",
                tab="assessment",
            )
        )

    # Affordability
    aff = case.chips.affordability
    facts["affordability"] = {"status": aff.status, "headroom": _fmt_paise(aff.headroom_paise)}
    citations.append(
        Citation(
            label="Affordability",
            detail=f"{aff.status} · headroom {_fmt_paise(aff.headroom_paise)}",
            tab="assessment",
        )
    )

    # Coverage
    cov = case.chips.coverage
    facts["coverage"] = {"score": cov.score, "band": cov.band}
    citations.append(
        Citation(label="Evidence coverage", detail=f"{cov.score} · {cov.band}", tab="assessment")
    )

    # Manipulation / verification
    facts["verification"] = case.chips.verification
    findings = [
        {"detector": f.detector_id, "statement": f.statement, "severity": f.severity}
        for f in case.manipulation_findings[:3]
    ]
    facts["manipulation_findings"] = findings
    citations.append(
        Citation(
            label="Verification",
            detail=case.chips.verification
            + (f" · {len(case.manipulation_findings)} finding(s)" if findings else " · none"),
            tab="verification",
        )
    )

    # Recourse + bureau-only counterfactual
    facts["recourse"] = [o.description for o in case.recourse[:3]]
    facts["bureau_only_counterfactual"] = {
        "outcome": case.bureau_only.outcome,
        "note": case.bureau_only.note,
    }
    if case.recourse:
        citations.append(
            Citation(
                label="Recourse",
                detail="; ".join(o.description for o in case.recourse[:2]),
                tab="recourse",
            )
        )
    return facts, citations


def _deterministic_answer(facts: dict[str, Any]) -> str:
    """A grounded, no-LLM explanation — always available, always true to the facts."""
    parts: list[str] = []
    outcome = facts.get("outcome")
    if outcome:
        rule = facts.get("decisive_rule")
        parts.append(
            f"This application was {outcome}"
            + (f", decided by the policy rule {rule}." if rule else ".")
        )
    risk = facts.get("risk", {})
    if risk.get("pd") is not None:
        factors = ", ".join(
            f"{f['feature']} ({'raises' if f['direction'] == 'PD_UP' else 'lowers'} risk)"
            for f in risk.get("top_factors", [])[:3]
        )
        parts.append(
            f"Risk PD is {risk['pd']:.3f} ({risk['calibration']} — a ranking, not a literal "
            f"probability){'; the biggest factors were ' + factors if factors else ''}."
        )
    aff = facts.get("affordability", {})
    if aff:
        parts.append(f"Affordability {aff['status']} with {aff['headroom']} monthly headroom.")
    cov = facts.get("coverage", {})
    if cov.get("score") is not None:
        parts.append(f"Evidence coverage is {cov['score']} ({cov['band']}).")
    if facts.get("reasons"):
        parts.append("Reasons on file: " + "; ".join(facts["reasons"][:3]) + ".")
    if facts.get("recourse"):
        parts.append("Possible recourse: " + "; ".join(facts["recourse"][:2]) + ".")
    return " ".join(parts) or "No decision has been recorded for this application yet."


async def explain_decision(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    application_id: uuid.UUID,
    question: str,
) -> DecisionExplanation:
    case = await assemble_case(session, tenant_id, application_id)
    facts, citations = _build_facts(case)
    clean_question = question.strip()[:500] or "Explain this decision."

    fallback = DecisionExplanation(
        answer=_deterministic_answer(facts), citations=citations, used_llm=False
    )
    if not settings.llm_notices_enabled:
        return fallback
    try:
        provider = configured_registry().llm(settings.llm_provider)
    except (ProviderNotConfigured, RuntimeError):
        return fallback
    try:
        parsed = await provider.complete(
            _SYSTEM, {"question": clean_question, "facts": facts}, _Explanation
        )
    except Exception as exc:  # provider/timeout/parse — degrade to the grounded summary
        logger.info("decision_explain_fallback", reason=type(exc).__name__)
        return fallback
    return DecisionExplanation(answer=parsed.answer.strip(), citations=citations, used_llm=True)
