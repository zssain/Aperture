"""Template-mode notice rendering.

Pure functions: given the decision, its reasons (from ``decision_reasons.template_params``) and a
language, produce the exact text the applicant receives. No LLM here (Prompt 18 adds it as an
optional, validated layer on top). The output states the decision + terms, up to three reasons in
plain language, and - for recourse - the action, a non-guarantee statement, and the expiry, with
no threshold ever quoted.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from app.services.notices.templates import (
    DECISION_COPY,
    DEFAULT_LANGUAGE,
    RECOURSE_COPY,
    SUPPORTED_LANGUAGES,
    lever_action,
    outcome_class,
    reason_phrase,
)

_MAX_REASONS = 3


@dataclass(frozen=True)
class RenderedNotice:
    subject: str
    body: str
    language: str
    template_version: str


def _lang(language: str) -> str:
    return language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def _rupees(paise: int) -> str:
    return f"{paise // 100:,}"


def render_decision_notice(
    *,
    outcome: str,
    terms: dict[str, Any] | None,
    reasons: list[dict[str, Any]],
    language: str,
) -> RenderedNotice:
    from app.services.notices.templates import NOTICE_TEMPLATE_VERSION

    lang = _lang(language)
    copy = DECISION_COPY[lang]
    klass = outcome_class(outcome)

    lines: list[str] = [copy[klass]]

    if klass == "approved" and terms:
        principal = terms.get("approved_principal_paise")
        if isinstance(principal, int) and principal > 0:
            lines.append(
                copy["terms"].format(
                    amount=_rupees(principal),
                    tenor=terms.get("approved_tenor_months", 0),
                    rate=int(terms.get("annual_rate_bps", 0)) // 100,
                )
            )

    picked = reasons[:_MAX_REASONS]
    if picked:
        lines.append(copy["reasons_heading"])
        lines.extend(f"- {reason_phrase(str(r.get('code', '')), lang)}" for r in picked)

    lines.append(copy["closing"])
    return RenderedNotice(
        subject=copy["subject"],
        body="\n".join(lines),
        language=lang,
        template_version=NOTICE_TEMPLATE_VERSION,
    )


def _format_expiry(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value)
    # Accept an ISO datetime string; fall back to the raw text.
    try:
        return datetime.fromisoformat(text).date().isoformat()
    except ValueError:
        return text


def render_recourse_notice(
    *,
    options: list[dict[str, Any]],
    language: str,
) -> RenderedNotice:
    from app.services.notices.templates import NOTICE_TEMPLATE_VERSION

    lang = _lang(language)
    copy = RECOURSE_COPY[lang]

    if not options:
        return RenderedNotice(
            subject=copy["subject"],
            body=copy["none"],
            language=lang,
            template_version=NOTICE_TEMPLATE_VERSION,
        )

    best = options[0]
    change = dict(best.get("required_change", {}))
    lever = str(change.get("lever", "ADD_SOURCE"))
    lines: list[str] = [
        copy["intro"],
        copy["action_line"].format(action=lever_action(lever, lang)),
        copy["no_guarantee"],
    ]
    expiry = change.get("expires_at")
    if expiry is not None:
        lines.append(copy["expiry"].format(date=_format_expiry(expiry)))

    return RenderedNotice(
        subject=copy["subject"],
        body="\n".join(lines),
        language=lang,
        template_version=NOTICE_TEMPLATE_VERSION,
    )
