"""Typed, explicit allow-list for the only data an LLM notice may receive."""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NoticeTerms(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    amount_paise: int | None = None
    tenor_months: int | None = None
    annual_rate_bps: int | None = None


class NoticeReason(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    label: str
    template_params: dict[str, int | float | str] = Field(default_factory=dict)


class NoticeRecourse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action: str
    projected_outcome: str | None = None


class NoticeContext(BaseModel):
    """No raw text fields exist: extra keys such as descriptions are rejected."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    outcome: str
    terms: NoticeTerms | None = None
    reasons: tuple[NoticeReason, ...] = Field(default=(), max_length=3)
    recourse: tuple[NoticeRecourse, ...] = Field(default=(), max_length=3)
    expiry_date: date | None = None
    applicant_display_name: str | None = Field(default=None, max_length=200)
    language: str


NOTICE_CONTEXT_FIELDS = frozenset(NoticeContext.model_fields)


def build_notice_context(
    *,
    outcome: str,
    terms: dict[str, Any] | None,
    reasons: list[dict[str, Any]],
    recourse: list[dict[str, Any]],
    expiry_date: date | None,
    applicant_display_name: str | None,
    language: str,
) -> NoticeContext:
    typed_terms = None
    if terms:
        typed_terms = NoticeTerms(
            amount_paise=terms.get("approved_principal_paise"),
            tenor_months=terms.get("approved_tenor_months"),
            annual_rate_bps=terms.get("annual_rate_bps"),
        )
    return NoticeContext(
        outcome=outcome,
        terms=typed_terms,
        reasons=tuple(
            NoticeReason(
                label=str(item.get("code", "")),
                template_params={
                    str(key): value
                    for key, value in dict(item.get("template_params") or {}).items()
                    if isinstance(value, (int, float, str))
                },
            )
            for item in reasons[:3]
        ),
        recourse=tuple(
            NoticeRecourse(
                action=str(dict(item.get("required_change") or {}).get("lever", "ADD_SOURCE")),
                projected_outcome=str(item["projected_action"])
                if item.get("projected_action")
                else None,
            )
            for item in recourse[:3]
        ),
        expiry_date=expiry_date,
        applicant_display_name=applicant_display_name,
        language=language,
    )
