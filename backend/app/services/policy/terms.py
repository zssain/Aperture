"""Terms ladder + graduation.

Every approval's principal is capped at ``min(band_max, affordability.max_supportable,
requested)`` - affordability ALWAYS binds (invariant: never approve above what the applicant
can service). The cap is reported (``approved_principal_paise``) so the recourse engine can
tell the applicant exactly what would change the answer.
"""

from typing import Any

from app.services.policy.schema import (
    AffordabilityInput,
    LoanRequest,
    PolicyRules,
    Terms,
    TermsBand,
)


def _graduation_dict(band: TermsBand) -> dict[str, Any] | None:
    if band.graduation is None:
        return None
    return band.graduation.model_dump(mode="json")


def build_terms(
    band_name: str,
    policy: PolicyRules,
    affordability: AffordabilityInput,
    request: LoanRequest,
) -> Terms:
    band = policy.terms[band_name]  # KeyError here = incomplete ladder (caught by validator)

    # Affordability binds. If PASS, max_supportable is a real number; guard defensively so a
    # None can never inflate the cap.
    supportable = affordability.max_supportable_principal_paise
    caps = [band.max_principal_paise, request.amount_paise]
    if supportable is not None:
        caps.append(supportable)
    approved_principal = max(0, min(caps))

    approved_tenor = min(band.max_tenor_months, request.tenor_months)

    return Terms(
        band=band_name,
        max_principal_paise=band.max_principal_paise,
        approved_principal_paise=approved_principal,
        max_tenor_months=band.max_tenor_months,
        approved_tenor_months=approved_tenor,
        rate_band=band.rate_band,
        annual_rate_bps=band.annual_rate_bps,
        graduation=_graduation_dict(band),
    )
