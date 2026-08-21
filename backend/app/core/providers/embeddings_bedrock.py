"""AWS Bedrock Titan embedding provider. AWS imports stay inside this boundary."""

import json
from typing import Any

import boto3
from botocore.config import Config

from app.core.config import Settings
from app.core.providers.base import EmbeddingDimensionError, ProviderResponseError


class BedrockEmbeddingProvider:
    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        if not settings.allow_external_embeddings:
            raise RuntimeError("external embeddings are disabled")
        self.model_id = settings.bedrock_embedding_model_id
        self.dimension = settings.embedding_dimension
        self._client = client or boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_region,
            config=Config(connect_timeout=5, read_timeout=5, retries={"max_attempts": 1}),
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        result: list[list[float]] = []
        for text in texts:
            response = self._client.invoke_model(
                modelId=self.model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(
                    {"inputText": text, "dimensions": self.dimension, "normalize": True}
                ),
            )
            body = json.loads(response["body"].read())
            vector = [round(float(value), 8) for value in body.get("embedding", [])]
            if len(vector) != self.dimension:
                raise EmbeddingDimensionError(
                    f"Bedrock returned {len(vector)} dimensions; expected {self.dimension}"
                )
            result.append(vector)
        if len(result) != len(texts):
            raise ProviderResponseError("Bedrock omitted an embedding")
        return result
