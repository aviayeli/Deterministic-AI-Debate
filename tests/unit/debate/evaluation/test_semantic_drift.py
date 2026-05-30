"""Phase 2a.2 — SemanticDriftEvaluator contract tests."""
from dataclasses import dataclass

import pytest

from src.debate.config import settings
from src.debate.engine.embeddings import EmbeddingService
from src.debate.evaluation.semantic_drift import DriftResult, SemanticDriftEvaluator


@dataclass
class _MockAgent:
    v1_embedding: list[float] | None


@pytest.fixture(scope="module")
def evaluator() -> SemanticDriftEvaluator:
    return SemanticDriftEvaluator(EmbeddingService(), settings)


def test_no_v1_penalty_when_distance_below_threshold(evaluator: SemanticDriftEvaluator) -> None:
    agent = _MockAgent(v1_embedding=[1.0, 0.0, 0.0])
    result = evaluator.evaluate(agent, [1.0, 0.0, 0.0], [])
    assert result.drift_penalty == pytest.approx(0.0, abs=1e-6)


def test_v1_penalty_when_distance_exceeds_threshold(evaluator: SemanticDriftEvaluator) -> None:
    # orthogonal vectors → cosine_distance = 1.0 > V1_DISTANCE_THRESHOLD (0.4)
    agent = _MockAgent(v1_embedding=[1.0, 0.0, 0.0])
    result = evaluator.evaluate(agent, [0.0, 1.0, 0.0], [])
    assert result.drift_penalty > 0.0


def test_no_centroid_penalty_when_alignment_below_threshold(
    evaluator: SemanticDriftEvaluator,
) -> None:
    # current=[1,0,0] vs opponent centroid=[0,1,0]: similarity=0 < 0.7
    agent = _MockAgent(v1_embedding=[1.0, 0.0, 0.0])
    result = evaluator.evaluate(agent, [1.0, 0.0, 0.0], [[0.0, 1.0, 0.0]])
    assert result.centroid_alignment < settings.CENTROID_ALIGNMENT_THRESHOLD
    assert result.drift_penalty == pytest.approx(0.0, abs=1e-6)


def test_centroid_penalty_when_alignment_exceeds_threshold(
    evaluator: SemanticDriftEvaluator,
) -> None:
    # current=[1,0,0] == opponent centroid=[1,0,0]: similarity=1.0 > 0.7
    agent = _MockAgent(v1_embedding=[0.0, 0.0, 1.0])
    result = evaluator.evaluate(agent, [1.0, 0.0, 0.0], [[1.0, 0.0, 0.0]])
    assert result.centroid_alignment > settings.CENTROID_ALIGNMENT_THRESHOLD
    assert result.drift_penalty > 0.0


def test_evaluate_reads_v1_from_agent_state(evaluator: SemanticDriftEvaluator) -> None:
    # current matches agent.v1_embedding → v1_distance must be 0.0
    agent = _MockAgent(v1_embedding=[1.0, 0.0, 0.0])
    result = evaluator.evaluate(agent, [1.0, 0.0, 0.0], [])
    assert result.v1_distance == pytest.approx(0.0, abs=1e-6)


def test_evaluate_raises_if_v1_embedding_is_none(evaluator: SemanticDriftEvaluator) -> None:
    agent = _MockAgent(v1_embedding=None)
    with pytest.raises(ValueError):
        evaluator.evaluate(agent, [1.0, 0.0, 0.0], [])


def test_decay_weights_favor_recent_embeddings(evaluator: SemanticDriftEvaluator) -> None:
    # opp = [[1,0,0](oldest), [0,1,0](newest)], λ=0.3 → weights [0.3, 1.0]
    # centroid ≈ [0.23, 0.77, 0] — closer to newest [0,1,0]
    # current matching newest → higher alignment than current matching oldest
    agent = _MockAgent(v1_embedding=[0.0, 0.0, 1.0])
    opp = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    near_new = evaluator.evaluate(agent, [0.0, 1.0, 0.0], opp)
    near_old = evaluator.evaluate(agent, [1.0, 0.0, 0.0], opp)
    assert near_new.centroid_alignment > near_old.centroid_alignment


def test_drift_result_has_required_fields(evaluator: SemanticDriftEvaluator) -> None:
    agent = _MockAgent(v1_embedding=[1.0, 0.0, 0.0])
    result = evaluator.evaluate(agent, [1.0, 0.0, 0.0], [])
    assert isinstance(result, DriftResult)
    assert hasattr(result, "v1_distance")
    assert hasattr(result, "centroid_alignment")
    assert hasattr(result, "drift_penalty")
