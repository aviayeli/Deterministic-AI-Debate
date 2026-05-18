import json
import re
from abc import ABC, abstractmethod
from typing import Any

from ..logging import get_logger
from ..schemas.claim import ClaimPayloadSchema
from ..schemas.round import LedgerEntry

_log = get_logger("agent_base")
_JSON_PARSE_RETRIES = 3


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

    @staticmethod
    def _extract_json(text: str) -> dict:
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                return json.loads(m.group())
            raise ValueError(f"No JSON object found in LLM response: {text!r}") from exc

    def _call_json(
        self, gatekeeper: Any, *, max_retries: int = _JSON_PARSE_RETRIES, **kwargs: Any
    ) -> tuple[Any, dict]:
        """Call the LLM, retrying on JSON parse failure (e.g. truncated output)."""
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            msg = gatekeeper.call(**kwargs)
            try:
                return msg, self._extract_json(msg.content[0].text)
            except (ValueError, json.JSONDecodeError) as exc:
                last_exc = exc
                _log.warning(
                    f"JSON parse attempt {attempt + 1}/{max_retries} failed: {exc!r}"
                )
        raise ValueError(
            f"JSON parse failed after {max_retries} attempts"
        ) from last_exc

    @abstractmethod
    def generate_claim(
        self, round_number: int, opponent_ledger: list[LedgerEntry]
    ) -> ClaimPayloadSchema: ...
