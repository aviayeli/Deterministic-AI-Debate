from src.debate.config import settings
from src.debate.engine.ledger import LedgerManager
from src.debate.gatekeeper import ApiGatekeeper
from src.debate.logging import get_logger
from src.debate.schemas.claim import ClaimPayloadSchema
from src.debate.schemas.round import LedgerEntry

from .base import BaseAgent

_log = get_logger("pro_agent")

_SYSTEM = (
    "You are a PRO debater arguing that AI WILL replace software engineers. "
    "You MUST respond with ONLY a raw JSON object — no markdown, no preamble, no explanation. "
    "Output nothing except this exact structure: "
    '{"claim_text": "<your argument>", "addressed_claim_ids": ["<id>", ...]}'
)
_SUFFIX = (
    " You MUST respond with ONLY a raw JSON object — no markdown, no preamble. "
    'Output: {"claim_text": "<your argument>", "addressed_claim_ids": ["<id>", ...]}'
)


class ProAgent(BaseAgent):
    def __init__(self, gatekeeper: ApiGatekeeper, topic: str | None = None) -> None:
        super().__init__()
        self._gatekeeper = gatekeeper
        self._system = (
            f"You are a PRO debater. Position: {topic} — AGREE.{_SUFFIX}"
            if topic else _SYSTEM
        )

    def generate_claim(
        self, round_number: int, opponent_ledger: list[LedgerEntry]
    ) -> ClaimPayloadSchema:
        context = LedgerManager(opponent_ledger).serialize_for_llm(
            window=settings.LEDGER_WINDOW
        )
        msg = self._gatekeeper.call(
            model=settings.LLM_MODEL,
            max_tokens=512,
            temperature=0,
            system=self._system,
            messages=[
                {
                    "role": "user",
                    "content": f"Round {round_number}. Opponent claims: {context}",
                }
            ],
        )
        used = msg.usage.input_tokens + msg.usage.output_tokens
        self._tokens += used
        _log.debug(f"Round {round_number} | tokens={used}")
        data = self._extract_json(msg.content[0].text)
        return ClaimPayloadSchema(
            agent_id="PRO",
            round_number=round_number,
            stance="PRO",
            claim_text=data["claim_text"],
            addressed_claim_ids=data.get("addressed_claim_ids", []),
        )
