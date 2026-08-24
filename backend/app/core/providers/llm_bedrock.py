"""AWS Bedrock Converse provider with a five-second budget and one jittered retry."""

import asyncio
import json
import random
import time
from collections import Counter
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from pydantic import ValidationError

from app.core.config import Settings
from app.core.providers.base import (
    ProviderResponseError,
    ProviderThrottled,
    ProviderUnavailable,
    SchemaT,
    assert_llm_payload_safe,
)

BEDROCK_CALLS: Counter[str] = Counter()


class BedrockLLMProvider:
    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self.model_id = settings.bedrock_model_id
        self.max_tokens = settings.llm_max_tokens
        if client is None:
            if boto3.Session().get_credentials() is None:
                raise ProviderUnavailable(
                    "AWS credentials are required when Bedrock notices are enabled"
                )
            client = boto3.client(
                "bedrock-runtime",
                region_name=settings.aws_region,
                config=Config(connect_timeout=5, read_timeout=5, retries={"max_attempts": 1}),
            )
        self._client = client

    def _converse(self, system: str, payload: dict[str, Any]) -> tuple[dict[str, Any], int, int]:
        assert_llm_payload_safe(payload)
        response = self._client.converse(
            modelId=self.model_id,
            system=[{"text": system}],
            messages=[
                {
                    "role": "user",
                    "content": [{"text": json.dumps(payload, sort_keys=True, default=str)}],
                }
            ],
            inferenceConfig={"maxTokens": self.max_tokens, "temperature": 0},
        )
        try:
            content = response["output"]["message"]["content"][0]["text"]
            parsed = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderResponseError("Bedrock returned malformed structured output") from exc
        usage = response.get("usage", {})
        return parsed, int(usage.get("inputTokens", 0)), int(usage.get("outputTokens", 0))

    async def complete(
        self, system: str, payload: dict[str, Any], schema: type[SchemaT]
    ) -> SchemaT:
        started = time.monotonic()
        last: BaseException | None = None
        for attempt in range(2):
            try:
                raw, input_tokens, output_tokens = await asyncio.wait_for(
                    asyncio.to_thread(self._converse, system, payload), timeout=2.35
                )
                result = schema.model_validate(raw)
                BEDROCK_CALLS[f"success:{self.model_id}"] += 1
                BEDROCK_CALLS[f"input_tokens:{input_tokens}"] += 1
                BEDROCK_CALLS[f"output_tokens:{output_tokens}"] += 1
                BEDROCK_CALLS[f"latency_ms:{round((time.monotonic() - started) * 1000)}"] += 1
                return result
            except ClientError as exc:
                last = exc
                code = str(exc.response.get("Error", {}).get("Code", ""))
                if code not in {"ThrottlingException", "TooManyRequestsException", "429"}:
                    break
                BEDROCK_CALLS["throttled"] += 1
                if attempt == 0:
                    await asyncio.sleep(random.uniform(0.03, 0.08))
            except (TimeoutError, OSError, ValidationError, ProviderResponseError) as exc:
                last = exc
                if attempt == 0:
                    await asyncio.sleep(random.uniform(0.03, 0.08))
        BEDROCK_CALLS["failure"] += 1
        if isinstance(last, ClientError):
            raise ProviderThrottled("Bedrock throttled after one retry") from last
        raise ProviderUnavailable("Bedrock unavailable after one retry") from last
