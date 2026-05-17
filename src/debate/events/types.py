"""Typed lifecycle event payloads for the debate EventBus."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..engine.pipeline import DebateResult

from ..schemas.claim import ClaimPayloadSchema
from ..schemas.round import RoundSchema

__all__ = [
    "AgentReplyEvent",
    "BeforeEvaluationEvent",
    "DebateEndEvent",
    "DebateStartEvent",
    "RoundEndEvent",
    "RoundStartEvent",
]


@dataclass
class DebateStartEvent:
    topic: str | None
    max_rounds: int


@dataclass
class RoundStartEvent:
    round_number: int
    max_rounds: int


@dataclass
class AgentReplyEvent:
    agent_id: str
    round_number: int
    claim: ClaimPayloadSchema


@dataclass
class RoundEndEvent:
    round_number: int
    round_schema: RoundSchema
    latency: float


@dataclass
class BeforeEvaluationEvent:
    rounds: list[RoundSchema]


@dataclass
class DebateEndEvent:
    result: DebateResult
