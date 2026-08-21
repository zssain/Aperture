"""Cross-layer failure modes remain explicit, fail-closed and atomic."""

import pytest
from app.core.providers.base import ProviderNotConfigured
from app.core.providers.noop import NoopEmbeddingProvider, NoopLLMProvider
from app.services.notices.validator import LLMNotice
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_orchestrator import (
    test_assessment_failure_persists_no_decision_and_raises as _assessment_failure,
)
from tests.test_orchestrator import (
    test_ledger_append_failure_rolls_back_decision as _ledger_failure,
)


async def test_provider_outages_are_explicit() -> None:
    with pytest.raises(ProviderNotConfigured):
        NoopEmbeddingProvider().embed(["narration"])
    with pytest.raises(ProviderNotConfigured):
        await NoopLLMProvider().complete("system", {"language": "en"}, LLMNotice)


async def test_mid_decision_and_ledger_failures_are_atomic(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _assessment_failure(db_session, monkeypatch)
    monkeypatch.undo()
    await _ledger_failure(db_session, monkeypatch)
