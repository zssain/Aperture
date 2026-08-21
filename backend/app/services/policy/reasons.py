"""Ordered decision-reason assembly from a versioned catalogue.

The gate that fired is ALWAYS the first reason - it is what actually determined the outcome.
After it come the top risk contributors, the coverage gaps, and the affordability facts. Each
reason carries a ``polarity`` and ``template_params`` so the notice renderer can format it in
any language without re-deriving anything (invariant 7: full traceability).
"""

from app.services.policy.schema import (
    AffordabilityInput,
    CoverageInput,
    FourAssessments,
    Polarity,
    PolicyOutcome,
    Reason,
    RiskInput,
)

REASONS_CATALOGUE_VERSION = "reasons-v1"

# Max number of risk contributors surfaced as reasons.
_TOP_CONTRIBUTORS = 3

# The gate reason code + polarity per outcome. Codes are stable and versioned.
_GATE_REASON: dict[PolicyOutcome, tuple[str, Polarity]] = {
    PolicyOutcome.FRAUD_REVIEW: ("GATE_FRAUD_REVIEW", Polarity.NEGATIVE),
    PolicyOutcome.DECLINE_AFFORDABILITY: ("GATE_DECLINE_AFFORDABILITY", Polarity.NEGATIVE),
    PolicyOutcome.REVIEW_EVIDENCE: ("GATE_REVIEW_EVIDENCE", Polarity.NEUTRAL),
    PolicyOutcome.REVIEW_FRAUD: ("GATE_REVIEW_FRAUD", Polarity.NEGATIVE),
    PolicyOutcome.DECLINE_RISK: ("GATE_DECLINE_RISK", Polarity.NEGATIVE),
    PolicyOutcome.APPROVE_ENHANCED: ("GATE_APPROVE_ENHANCED", Polarity.POSITIVE),
    PolicyOutcome.APPROVE_STANDARD: ("GATE_APPROVE_STANDARD", Polarity.POSITIVE),
    PolicyOutcome.APPROVE_STARTER: ("GATE_APPROVE_STARTER", Polarity.POSITIVE),
    PolicyOutcome.SYSTEM_UNAVAILABLE: ("GATE_SYSTEM_UNAVAILABLE", Polarity.NEUTRAL),
}

# The full set of codes this catalogue can emit (asserted complete by a test).
REASON_CODES: frozenset[str] = frozenset(
    {code for code, _ in _GATE_REASON.values()}
    | {
        "EXPLORATION_COHORT",
        "MANDATORY_REVIEW",
        "RISK_CONTRIBUTOR",
        "COVERAGE_GAP",
        "AFFORDABILITY_DSR",
        "AFFORDABILITY_MAX_PRINCIPAL",
    }
)


def _risk_reasons(risk: RiskInput) -> list[Reason]:
    if risk.pd is None or not risk.top_contributors:
        return []
    ranked = sorted(risk.top_contributors, key=lambda c: -abs(c.contribution))
    reasons: list[Reason] = []
    for contributor in ranked[:_TOP_CONTRIBUTORS]:
        polarity = (
            Polarity.NEGATIVE if contributor.direction == "increases_risk" else Polarity.POSITIVE
        )
        reasons.append(
            Reason(
                code="RISK_CONTRIBUTOR",
                polarity=polarity.value,
                template_params={
                    "feature": contributor.feature,
                    "contribution": round(contributor.contribution, 6),
                    "direction": contributor.direction,
                },
            )
        )
    return reasons


def _coverage_reasons(coverage: CoverageInput) -> list[Reason]:
    gaps = sorted(coverage.missing_sources, key=lambda m: -m.coverage_delta)
    return [
        Reason(
            code="COVERAGE_GAP",
            polarity=Polarity.NEGATIVE.value,
            template_params={
                "source_type": gap.source_type,
                "coverage_delta": gap.coverage_delta,
            },
        )
        for gap in gaps
    ]


def _affordability_reasons(affordability: AffordabilityInput) -> list[Reason]:
    reasons: list[Reason] = []
    if affordability.dsr is not None and affordability.dsr_ceiling is not None:
        reasons.append(
            Reason(
                code="AFFORDABILITY_DSR",
                polarity=Polarity.NEUTRAL.value,
                template_params={
                    "dsr": round(affordability.dsr, 6),
                    "dsr_ceiling": affordability.dsr_ceiling,
                },
            )
        )
    if affordability.max_supportable_principal_paise is not None:
        reasons.append(
            Reason(
                code="AFFORDABILITY_MAX_PRINCIPAL",
                polarity=Polarity.NEUTRAL.value,
                template_params={
                    "max_supportable_principal_paise": (
                        affordability.max_supportable_principal_paise
                    ),
                },
            )
        )
    return reasons


def assemble_reasons(
    outcome: PolicyOutcome,
    assessments: FourAssessments,
    *,
    exploration_cohort: bool,
    mandatory_review: bool,
) -> tuple[Reason, ...]:
    """The gate reason first, then risk contributors, coverage gaps, affordability facts."""
    assert assessments.risk is not None
    assert assessments.coverage is not None
    assert assessments.affordability is not None

    code, polarity = _GATE_REASON[outcome]
    reasons: list[Reason] = [Reason(code=code, polarity=polarity.value)]

    if exploration_cohort:
        reasons.append(Reason(code="EXPLORATION_COHORT", polarity=Polarity.POSITIVE.value))
    if mandatory_review:
        reasons.append(Reason(code="MANDATORY_REVIEW", polarity=Polarity.NEUTRAL.value))

    reasons.extend(_risk_reasons(assessments.risk))
    reasons.extend(_coverage_reasons(assessments.coverage))
    reasons.extend(_affordability_reasons(assessments.affordability))
    return tuple(reasons)
