from pydantic import BaseModel

from .claim import ClaimPayloadSchema


class LedgerEntry(BaseModel):
    claim: ClaimPayloadSchema
    embedding: list[float] | None = None


class RoundSchema(BaseModel):
    round_number: int
    pro_claim: ClaimPayloadSchema
    con_claim: ClaimPayloadSchema
    responsiveness_score_pro: float
    responsiveness_score_con: float
