from abc import ABC, abstractmethod

from src.debate.schemas.claim import ClaimPayloadSchema
from src.debate.schemas.round import LedgerEntry


class BaseAgent(ABC):
    def __init__(self) -> None:
        self.v1_embedding: list[float] | None = None
        self._ledger: list[LedgerEntry] = []
        self._tokens: int = 0
        self._cache_hits: int = 0

    def set_v1_embedding(self, emb: list[float]) -> None:
        if self.v1_embedding is not None:
            raise RuntimeError("V₁ embedding is immutable; set_v1_embedding called twice.")
        self.v1_embedding = emb

    def add_to_ledger(self, entry: LedgerEntry) -> None:
        self._ledger.append(entry)

    def get_windowed_ledger(self, n: int) -> list[LedgerEntry]:
        return self._ledger[-n:]

    @abstractmethod
    def generate_claim(
        self, round_number: int, opponent_ledger: list[LedgerEntry]
    ) -> ClaimPayloadSchema: ...
