from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer

from src.debate.config import settings


class EmbeddingService:
    _instance: EmbeddingService | None = None
    _initialized: bool = False

    def __new__(cls) -> EmbeddingService:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._model: SentenceTransformer = SentenceTransformer(
            settings.EMBEDDING_MODEL
        )
        self._initialized = True

    def embed(self, text: str) -> list[float]:
        return self._model.encode(text, convert_to_numpy=True).tolist()

    def cosine_similarity(self, a: list[float], b: list[float]) -> float:
        va, vb = np.array(a), np.array(b)
        denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
        if denom == 0.0:
            return 0.0
        return float(np.dot(va, vb) / denom)

    def cosine_distance(self, a: list[float], b: list[float]) -> float:
        return 1.0 - self.cosine_similarity(a, b)

    def weighted_centroid(
        self,
        embeddings: list[list[float]],
        weights: list[float],
    ) -> list[float]:
        arr = np.array(embeddings)
        w = np.array(weights)
        return np.average(arr, axis=0, weights=w).tolist()
