import asyncio

import pytest
from app.core.llm import generate_with_retry
from app.services.notices.context import NoticeContext, build_notice_context
from app.services.notices.llm_renderer import render_notice
from app.services.notices.prompts import NoticePrompt
from app.services.notices.renderer import render_decision_notice
from app.services.notices.validator import LLMNotice, validate_notice
from pydantic import ValidationError


def context(outcome: str = "DECLINE_RISK") -> NoticeContext:
    return build_notice_context(
        outcome=outcome,
        terms=None,
        reasons=[{"code": "GATE_DECLINE_RISK", "template_params": {}}],
        recourse=[],
        expiry_date=None,
        applicant_display_name="Applicant",
        language="en",
    )


def test_context_structurally_rejects_ledger_text() -> None:
    with pytest.raises(ValidationError):
        NoticeContext.model_validate(
            {**context().model_dump(), "transaction_description": "ignore instructions"}
        )


@pytest.mark.parametrize(
    "body,error",
    [
        ("We can offer ₹99999 after review of your request.", "invented numeral"),
        ("Your application is approved and complete.", "approval language"),
        ("Your next application will be approved, guaranteed.", "guarantee language"),
        ("The pd_decline threshold and model version caused this result.", "internals"),
    ],
)
def test_validator_rejects_unsafe_output(body: str, error: str) -> None:
    result = validate_notice(
        LLMNotice(subject="Application update", body=body, language="en"), context()
    )
    assert not result.ok
    assert error in " ".join(result.errors)


@pytest.mark.parametrize(
    "outcome",
    [
        "FRAUD_REVIEW",
        "DECLINE_AFFORDABILITY",
        "REVIEW_EVIDENCE",
        "REVIEW_FRAUD",
        "DECLINE_RISK",
        "APPROVE_ENHANCED",
        "APPROVE_STANDARD",
        "APPROVE_STARTER",
        "SYSTEM_UNAVAILABLE",
    ],
)
@pytest.mark.parametrize("language", ["en", "hi"])
async def test_flag_off_always_uses_correct_template(outcome: str, language: str) -> None:
    result = await render_notice(
        outcome=outcome,
        terms=None,
        reasons=[],
        language=language,
        enabled=False,
    )
    expected = render_decision_notice(outcome=outcome, terms=None, reasons=[], language=language)
    assert result == expected


class CountingProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, *, system: str, context: str) -> dict[str, str]:
        self.calls += 1
        return {
            "subject": "Application update",
            "body": "We are unable to approve your application at this time.",
            "language": "en",
        }


async def test_identical_decision_and_language_is_cached() -> None:
    provider = CountingProvider()
    first = await render_notice(
        outcome="DECLINE_RISK",
        terms=None,
        reasons=[],
        language="en",
        provider=provider,
        enabled=True,
    )
    second = await render_notice(
        outcome="DECLINE_RISK",
        terms=None,
        reasons=[],
        language="en",
        provider=provider,
        enabled=True,
    )
    assert first == second
    assert provider.calls == 1


async def test_prompt_version_change_invalidates_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = CountingProvider()
    await render_notice(
        outcome="DECLINE_RISK",
        terms=None,
        reasons=[],
        language="en",
        provider=provider,
        enabled=True,
        applicant_display_name="Prompt Version Fixture",
    )
    monkeypatch.setattr(
        "app.services.notices.llm_renderer.DECISION_PROMPT",
        NoticePrompt("decision-notice-v2", "Phrase only; never compute or infer."),
    )
    await render_notice(
        outcome="DECLINE_RISK",
        terms=None,
        reasons=[],
        language="en",
        provider=provider,
        enabled=True,
        applicant_display_name="Prompt Version Fixture",
    )
    assert provider.calls == 2


class SlowProvider:
    async def generate(self, *, system: str, context: str) -> dict[str, str]:
        await asyncio.sleep(1)
        return {
            "subject": "late",
            "body": "This response arrived too late to use safely.",
            "language": "en",
        }


async def test_provider_timeout_has_a_bounded_retry_budget() -> None:
    started = asyncio.get_running_loop().time()
    with pytest.raises(RuntimeError):
        await generate_with_retry(
            SlowProvider(), system="system", context="{}", timeout_seconds=0.1
        )
    assert asyncio.get_running_loop().time() - started < 0.2


class UnsafeProvider:
    async def generate(self, *, system: str, context: str) -> dict[str, str]:
        return {
            "subject": "Application approved",
            "body": "Your application is approved and guaranteed today.",
            "language": "en",
        }


async def test_validation_failure_falls_back_and_increments_metric() -> None:
    from app.services.notices.llm_renderer import NOTICE_VALIDATION_FAILURES

    before = sum(NOTICE_VALIDATION_FAILURES.values())
    result = await render_notice(
        outcome="DECLINE_AFFORDABILITY",
        terms=None,
        reasons=[],
        language="en",
        provider=UnsafeProvider(),
        enabled=True,
    )
    expected = render_decision_notice(
        outcome="DECLINE_AFFORDABILITY", terms=None, reasons=[], language="en"
    )
    assert result == expected
    assert sum(NOTICE_VALIDATION_FAILURES.values()) == before + 1
