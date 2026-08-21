import json
import time

import pytest
from app.core.config import Settings
from app.core.providers.base import ProviderResponseError, ProviderThrottled, ProviderUnavailable
from app.core.providers.llm_bedrock import BedrockLLMProvider
from app.services.notices.validator import LLMNotice
from botocore.exceptions import ClientError


class Client:
    def converse(self, **request: object) -> dict[str, object]:
        del request
        return {
            "output": {
                "message": {
                    "content": [
                        {
                            "text": json.dumps(
                                {
                                    "subject": "Update",
                                    "body": "We cannot approve the application at this time.",
                                    "language": "en",
                                }
                            )
                        }
                    ]
                }
            },
            "usage": {"inputTokens": 4, "outputTokens": 8},
        }


def config() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://x:x@localhost/x",
        frontend_origin="http://localhost:5173",
    )


async def test_bedrock_converse_structured_success() -> None:
    result = await BedrockLLMProvider(config(), Client()).complete(
        "system",
        {
            "outcome": "DECLINE_RISK",
            "terms": None,
            "reasons": [],
            "recourse": [],
            "expiry_date": None,
            "applicant_display_name": None,
            "language": "en",
        },
        LLMNotice,
    )
    assert result.language == "en"


async def test_provider_rejects_new_context_field_before_egress() -> None:
    provider = BedrockLLMProvider(config(), Client())
    with pytest.raises(ProviderResponseError):
        provider._converse("system", {"outcome": "x", "description": "attacker text"})


class ThrottleClient:
    def __init__(self) -> None:
        self.calls = 0

    def converse(self, **request: object) -> dict[str, object]:
        del request
        self.calls += 1
        raise ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "slow down"}},
            "Converse",
        )


async def test_throttling_has_one_backoff_then_fails() -> None:
    client = ThrottleClient()
    provider = BedrockLLMProvider(config(), client)
    with pytest.raises(ProviderThrottled):
        await provider.complete("system", {}, LLMNotice)
    assert client.calls == 2


class SlowClient:
    def converse(self, **request: object) -> dict[str, object]:
        del request
        time.sleep(3)
        return {}


async def test_provider_timeout_finishes_inside_five_second_budget() -> None:
    started = time.monotonic()
    with pytest.raises(ProviderUnavailable):
        await BedrockLLMProvider(config(), SlowClient()).complete("system", {}, LLMNotice)
    assert time.monotonic() - started < 5.0
