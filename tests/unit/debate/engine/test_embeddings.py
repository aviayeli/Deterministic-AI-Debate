"""Phase 2a.1 — EmbeddingService contract tests."""
import pytest

from src.debate.engine.embeddings import EmbeddingService

EMBED_DIM = 384  # all-MiniLM-L6-v2 output dimension


@pytest.fixture(scope="module")
def svc() -> EmbeddingService:
    return EmbeddingService()


def test_embed_returns_list_of_floats(svc: EmbeddingService) -> None:
    result = svc.embed("hello world")
    assert isinstance(result, list)
    assert all(isinstance(v, float) for v in result)


def test_embed_dimension_is_384(svc: EmbeddingService) -> None:
    assert len(svc.embed("test sentence")) == EMBED_DIM


def test_embed_is_deterministic(svc: EmbeddingService) -> None:
    text = "AI will transform software development."
    assert svc.embed(text) == svc.embed(text)


def test_cosine_distance_identical_vectors_is_zero(svc: EmbeddingService) -> None:
    v = [1.0, 0.0, 0.0]
    assert svc.cosine_distance(v, v) == pytest.approx(0.0, abs=1e-6)


def test_cosine_distance_unrelated_texts(svc: EmbeddingService) -> None:
    a = svc.embed("AI automation replaces software engineers")
    b = svc.embed("apple pie recipe with cinnamon")
    assert svc.cosine_distance(a, b) > 0.5


def test_cosine_similarity_identical_vectors_is_one(svc: EmbeddingService) -> None:
    v = [0.0, 1.0, 0.0]
    assert svc.cosine_similarity(v, v) == pytest.approx(1.0, abs=1e-6)


def test_weighted_centroid_single_vector(svc: EmbeddingService) -> None:
    v = [1.0, 2.0, 3.0]
    assert svc.weighted_centroid([v], [1.0]) == pytest.approx(v, abs=1e-6)


def test_weighted_centroid_uniform_weights_equals_mean(svc: EmbeddingService) -> None:
    a = [2.0, 0.0]
    b = [0.0, 2.0]
    result = svc.weighted_centroid([a, b], [1.0, 1.0])
    assert result == pytest.approx([1.0, 1.0], abs=1e-6)


def test_embedding_service_is_singleton() -> None:
    svc1 = EmbeddingService()
    svc2 = EmbeddingService()
    assert svc1 is svc2
