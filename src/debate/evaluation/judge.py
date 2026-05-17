import hashlib
import random
from typing import Any

from ..schemas.round import LedgerEntry, RoundSchema
from ..schemas.verdict import VerdictSchema


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _mean_ev_quality(ledger: list[LedgerEntry]) -> float:
    scores = [ev.quality_score for e in ledger for ev in e.claim.evidence]
    return _mean(scores) if scores else 0.5


def _v1_distance(agent: Any) -> float:
    ledger: list[LedgerEntry] = getattr(agent, "_ledger", [])
    v1: list[float] | None = getattr(agent, "v1_embedding", None)
    if not ledger or v1 is None or ledger[-1].embedding is None:
        return 0.0
    from ..engine.embeddings import EmbeddingService

    return EmbeddingService().cosine_distance(ledger[-1].embedding, v1)


class Judge:
    def evaluate_debate(
        self,
        rounds: list[RoundSchema],
        pro_agent: Any,
        con_agent: Any,
        debate_id: str = "",
    ) -> VerdictSchema:
        pro_resp = _mean([r.responsiveness_score_pro for r in rounds])
        con_resp = _mean([r.responsiveness_score_con for r in rounds])
        ev_pro = _mean_ev_quality(getattr(pro_agent, "_ledger", []))
        ev_con = _mean_ev_quality(getattr(con_agent, "_ledger", []))
        v1_pro = _v1_distance(pro_agent)
        v1_con = _v1_distance(con_agent)

        winner, tiebreaker = self._resolve(
            pro_resp, con_resp, ev_pro, ev_con, v1_pro, v1_con, debate_id
        )
        return VerdictSchema(
            winner=winner,
            pro_score=pro_resp,
            con_score=con_resp,
            tiebreaker_used=tiebreaker,
            evidence_quality_pro=ev_pro,
            evidence_quality_con=ev_con,
            v1_distance_pro=v1_pro,
            v1_distance_con=v1_con,
            responsiveness_pro=pro_resp,
            responsiveness_con=con_resp,
            reasoning=f"{winner} won with higher composite score.",
        )

    def _resolve(
        self,
        pro: float,
        con: float,
        ev_pro: float,
        ev_con: float,
        v1_pro: float,
        v1_con: float,
        debate_id: str,
    ) -> tuple[str, str | None]:
        if abs(pro - con) > 1e-9:
            return ("PRO" if pro > con else "CON", None)
        if abs(ev_pro - ev_con) > 1e-9:
            return ("PRO" if ev_pro > ev_con else "CON", "evidence_quality")
        if abs(v1_pro - v1_con) > 1e-9:
            return ("PRO" if v1_pro < v1_con else "CON", "v1_faithfulness")
        seed = int(hashlib.sha256(debate_id.encode()).hexdigest(), 16) % (2**32)
        return ("PRO" if random.Random(seed).random() < 0.5 else "CON", "prng")
