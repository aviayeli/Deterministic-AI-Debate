from typing import Any

from ..config import settings
from ..engine.ledger import LedgerManager
from ..gatekeeper import ApiGatekeeper
from ..logging import get_logger
from ..schemas.claim import ClaimPayloadSchema
from ..schemas.round import LedgerEntry
from .base import BaseAgent

_log = get_logger("con_agent")

_SYSTEM = (
    "You are a CON debater arguing that AI will NOT replace software engineers. "
    "Keep your arguments under 200 words to ensure complete JSON output. "
    "You MUST respond with ONLY a raw JSON object — no markdown, no preamble, no explanation. "
    "Output nothing except this exact structure: "
    '{"claim_text": "<your argument>", "addressed_claim_ids": ["<id>", ...]}'
)
_SUFFIX = (
    " Keep your arguments under 200 words to ensure complete JSON output. "
    "You MUST respond with ONLY a raw JSON object — no markdown, no preamble. "
    'Output: {"claim_text": "<your argument>", "addressed_claim_ids": ["<id>", ...]}'
)


class ConAgent(BaseAgent):
    def __init__(
        self, gatekeeper: ApiGatekeeper, topic: str | None = None, search_tool: Any = None
    ) -> None:
        super().__init__()
        self._gatekeeper = gatekeeper
        self._search_tool = search_tool
        self._system = (
            f"You are a CON debater. Position: {topic} — DISAGREE.{_SUFFIX}"
            if topic else _SYSTEM
        )

    def generate_claim(
        self, round_number: int, opponent_ledger: list[LedgerEntry]
    ) -> ClaimPayloadSchema:
        context = LedgerManager(opponent_ledger).serialize_for_llm(
            window=settings.LEDGER_WINDOW
        )
        facts = self._search_facts("AI replacing software engineers limitations evidence")
        search_ctx = f" Background facts: {facts}" if facts else ""
        msg, data = self._call_json(
            self._gatekeeper,
            model=settings.LLM_MODEL,
            max_tokens=8192,
            temperature=0,
            system=self._system,
            messages=[
                {
                    "role": "user",
                    "content": f"Round {round_number}. Opponent claims: {context}{search_ctx}",
                }
            ],
        )
        used = msg.usage.input_tokens + msg.usage.output_tokens
        self._tokens += used
        _log.debug(f"Round {round_number} | tokens={used}")
        return ClaimPayloadSchema(
            agent_id="CON",
            round_number=round_number,
            stance="CON",
            claim_text=data["claim_text"],
            addressed_claim_ids=data.get("addressed_claim_ids", []),
        )
