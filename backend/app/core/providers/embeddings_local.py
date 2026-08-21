"""Local sentence-transformers provider (the deployment default; no data egress)."""

import os
from typing import Any

from app.core.providers.base import EmbeddingDimensionError


class LocalEmbeddingProvider:
    def __init__(self, model_id: str, dimension: int) -> None:
        self._model_id = model_id
        self._dimension = dimension
        self._model: Any | None = None

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(
                self._model_id,
                cache_folder=os.environ.get("HF_HOME"),
            )
        raw = self._model.encode(texts, normalize_embeddings=True)
        vectors = [[round(float(value), 8) for value in row] for row in raw]
        if any(len(row) != self.dimension for row in vectors):
            raise EmbeddingDimensionError(
                f"model {self.model_id} did not return configured dimension {self.dimension}"
            )
        return vectors
