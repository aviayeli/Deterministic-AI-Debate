from typing import Literal

from pydantic import BaseModel


class VerdictSchema(BaseModel):
    winner: Literal["PRO", "CON"]
    pro_score: float
    con_score: float
    tiebreaker_used: str | None = None
    evidence_quality_pro: float
    evidence_quality_con: float
    v1_distance_pro: float
    v1_distance_con: float
    responsiveness_pro: float
    responsiveness_con: float
    reasoning: str
