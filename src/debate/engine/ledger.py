import json

from src.debate.schemas.round import LedgerEntry


class LedgerManager:
    def __init__(self, entries: list[LedgerEntry]) -> None:
        self._entries = entries

    def get_windowed_ledger(self, n: int) -> list[LedgerEntry]:
        return self._entries[-n:]

    def serialize_for_llm(self, window: int) -> str:
        return json.dumps(
            [
                {"claim_id": e.claim.claim_id, "claim_text": e.claim.claim_text}
                for e in self.get_windowed_ledger(window)
            ]
        )

    def get_claim_ids(self) -> set[str]:
        return {e.claim.claim_id for e in self._entries}

    def compute_weights(self, lam: float) -> list[float]:
        n = len(self._entries)
        weights: list[float] = []
        for i, entry in enumerate(self._entries):
            decay = lam ** (n - 1 - i)
            evs = entry.claim.evidence
            confidence = (
                sum(ev.quality_score for ev in evs) / len(evs) if evs else 1.0
            )
            weights.append(decay * confidence)
        return weights
