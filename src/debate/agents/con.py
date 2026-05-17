import anthropic

from src.debate.config import settings
from src.debate.engine.ledger import LedgerManager
from src.debate.schemas.claim import ClaimPayloadSchema
from src.debate.schemas.round import LedgerEntry

from .base import BaseAgent

_SYSTEM = (
    "You are a CON debater arguing that AI will NOT replace software engineers. "
    "You MUST respond with ONLY a raw JSON object — no markdown, no preamble, no explanation. "
    "Output nothing except this exact structure: "
    '{"claim_text": "<your argument>", "addressed_claim_ids": ["<id>", ...]}'
)


class ConAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__()
        self._client: anthropic.Anthropic | None = None

    def _client_or_init(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        return self._client

    def generate_claim(
        self, round_number: int, opponent_ledger: list[LedgerEntry]
    ) -> ClaimPayloadSchema:
        context = LedgerManager(opponent_ledger).serialize_for_llm(
            window=settings.LEDGER_WINDOW
        )
        msg = self._client_or_init().messages.create(
            model=settings.LLM_MODEL,
            max_tokens=512,
            temperature=0,
            system=_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": f"Round {round_number}. Opponent claims: {context}",
                }
            ],
        )
        self._tokens += msg.usage.input_tokens + msg.usage.output_tokens
        data = self._extract_json(msg.content[0].text)
        return ClaimPayloadSchema(
            agent_id="CON",
            round_number=round_number,
            stance="CON",
            claim_text=data["claim_text"],
            addressed_claim_ids=data.get("addressed_claim_ids", []),
        )
