from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class EvidenceSchema(BaseModel):
    source: str
    quality_score: float = Field(ge=0.0, le=1.0)
    citation: str


class ClaimPayloadSchema(BaseModel):
    claim_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_id: str
    round_number: int = Field(ge=1)
    stance: Literal["PRO", "CON"]
    claim_text: str
    addressed_claim_ids: list[str]
    evidence: list[EvidenceSchema] = Field(default_factory=list)
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
