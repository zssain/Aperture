"""Small provider boundary with one retry and a hard timeout."""

import asyncio
from typing import Any, Protocol


class LLMProvider(Protocol):
    async def generate(self, *, system: str, context: str) -> dict[str, Any] | str: ...


class LLMUnavailableError(RuntimeError):
    pass


async def generate_with_retry(
    provider: LLMProvider, *, system: str, context: str, timeout_seconds: float = 5.0
) -> dict[str, Any] | str:
    last: BaseException | None = None
    # Leave a little budget for retry scheduling and fallback construction so the
    # caller observes a result inside the advertised wall-clock limit.
    per_attempt_seconds = timeout_seconds / 2.1
    for _ in range(2):
        try:
            return await asyncio.wait_for(
                provider.generate(system=system, context=context), timeout=per_attempt_seconds
            )
        except (TimeoutError, OSError, ValueError) as exc:
            last = exc
    raise LLMUnavailableError("notice provider unavailable after one retry") from last
