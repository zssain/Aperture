"""Optional language-model renderer with permanent deterministic fallback."""

import asyncio
import hashlib
import json
from collections import Counter
from datetime import date
from typing import Any, Protocol, runtime_checkable

from pydantic import ValidationError

from app.core.config import settings
from app.core.logging import get_logger
from app.core.providers.base import LLMProvider
from app.core.providers.registry import configured_registry
from app.services.notices.context import build_notice_context
from app.services.notices.prompts import DECISION_PROMPT
from app.services.notices.renderer import RenderedNotice, render_decision_notice
from app.services.notices.templates import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES
from app.services.notices.validator import LLMNotice, validate_notice

logger = get_logger(__name__)
NOTICE_VALIDATION_FAILURES: Counter[str] = Counter()
_CACHE: dict[tuple[str, str, str], RenderedNotice] = {}


@runtime_checkable
class LegacyLLMProvider(Protocol):
    async def generate(self, *, system: str, context: str) -> dict[str, Any] | str: ...


def _hash(
    outcome: str,
    terms: dict[str, Any] | None,
    reasons: list[dict[str, Any]],
    recourse: list[dict[str, Any]],
    expiry_date: date | None,
    applicant_display_name: str | None,
) -> str:
    raw = json.dumps(
        {
            "outcome": outcome,
            "terms": terms,
            "reasons": reasons[:3],
            "recourse": recourse[:3],
            "expiry_date": expiry_date,
            "applicant_display_name": applicant_display_name,
        },
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode()).hexdigest()


async def render_notice(
    *,
    outcome: str,
    terms: dict[str, Any] | None,
    reasons: list[dict[str, Any]],
    recourse: list[dict[str, Any]] | None = None,
    expiry_date: date | None = None,
    applicant_display_name: str | None = None,
    language: str = "en",
    provider: LLMProvider | LegacyLLMProvider | None = None,
    enabled: bool | None = None,
) -> RenderedNotice:
    recourse = recourse or []
    fallback_language = language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    fallback = render_decision_notice(
        outcome=outcome, terms=terms, reasons=reasons, language=fallback_language
    )
    if language not in SUPPORTED_LANGUAGES and provider is None:
        NOTICE_VALIDATION_FAILURES["unsupported_language"] += 1
        return fallback
    use_llm = settings.llm_notices_enabled if enabled is None else enabled
    if use_llm and provider is None:
        try:
            provider = configured_registry().llm(settings.llm_provider)
        except RuntimeError:
            NOTICE_VALIDATION_FAILURES["provider_not_configured"] += 1
            return fallback
    if not use_llm or provider is None:
        return fallback
    decision_hash = _hash(
        outcome, terms, reasons, recourse, expiry_date, applicant_display_name
    )
    cache_key = (decision_hash, language, DECISION_PROMPT.prompt_version)
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    try:
        context = build_notice_context(
            outcome=outcome,
            terms=terms,
            reasons=reasons,
            recourse=recourse,
            expiry_date=expiry_date,
            applicant_display_name=applicant_display_name,
            language=language,
        )
        payload = context.model_dump(mode="json")
        if isinstance(provider, LegacyLLMProvider):
            # Transitional adapter for deployments implementing the pre-revision
            # interface. It is validated identically and can be removed after rollout.
            raw = await asyncio.wait_for(
                provider.generate(system=DECISION_PROMPT.system, context=context.model_dump_json()),
                timeout=settings.llm_notice_timeout_seconds,
            )
            if not isinstance(raw, dict):
                raise ValueError("provider returned prose instead of structured JSON")
            parsed = LLMNotice.model_validate(raw)
        else:
            parsed = await asyncio.wait_for(
                provider.complete(DECISION_PROMPT.system, payload, LLMNotice),
                timeout=settings.llm_notice_timeout_seconds,
            )
        validation = validate_notice(parsed, context)
        if not validation.ok:
            raise ValueError("; ".join(validation.errors))
        result = RenderedNotice(
            subject=parsed.subject,
            body=parsed.body,
            language=parsed.language,
            template_version=DECISION_PROMPT.prompt_version,
        )
        _CACHE[cache_key] = result
        return result
    except (ValueError, ValidationError, OSError, TimeoutError, RuntimeError) as exc:
        reason = type(exc).__name__
        NOTICE_VALIDATION_FAILURES[reason] += 1
        logger.warning("notice_llm_fallback", reason=reason)
        return fallback
