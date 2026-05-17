from pydantic import BaseModel

from ..config import Settings
from ..engine.embeddings import EmbeddingService


class DriftResult(BaseModel):
    v1_distance: float
    centroid_alignment: float
    drift_penalty: float


class SemanticDriftEvaluator:
    def __init__(self, embeddings: EmbeddingService, cfg: Settings) -> None:
        self._emb = embeddings
        self._cfg = cfg

    def evaluate(
        self,
        agent: object,
        current_embedding: list[float],
        opponent_embeddings: list[list[float]],
    ) -> DriftResult:
        v1: list[float] | None = getattr(agent, "v1_embedding", None)
        if v1 is None:
            raise ValueError(
                "agent.v1_embedding is None; set_v1_embedding must be called first."
            )
        v1_distance = self._emb.cosine_distance(current_embedding, v1)
        centroid_alignment = self._centroid_alignment(
            current_embedding, opponent_embeddings
        )
        return DriftResult(
            v1_distance=v1_distance,
            centroid_alignment=centroid_alignment,
            drift_penalty=self._penalty(v1_distance, centroid_alignment),
        )

    def _centroid_alignment(
        self,
        current: list[float],
        opponent_embeddings: list[list[float]],
    ) -> float:
        if not opponent_embeddings:
            return 0.0
        n = len(opponent_embeddings)
        weights = [self._cfg.RECENCY_DECAY_LAMBDA ** (n - 1 - i) for i in range(n)]
        centroid = self._emb.weighted_centroid(opponent_embeddings, weights)
        return self._emb.cosine_similarity(current, centroid)

    def _penalty(self, v1_distance: float, centroid_alignment: float) -> float:
        v1_pen = max(0.0, v1_distance - self._cfg.V1_DISTANCE_THRESHOLD)
        cent_pen = max(0.0, centroid_alignment - self._cfg.CENTROID_ALIGNMENT_THRESHOLD)
        return v1_pen + cent_pen
