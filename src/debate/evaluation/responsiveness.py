from ..schemas.claim import ClaimPayloadSchema
from ..schemas.round import LedgerEntry


class ResponsivenessCalculator:
    def calculate(
        self,
        claim: ClaimPayloadSchema,
        opponent_ledger: list[LedgerEntry],
    ) -> float:
        if not opponent_ledger:
            return 0.0
        opponent_ids = {e.claim.claim_id for e in opponent_ledger}
        valid = set(claim.addressed_claim_ids) & opponent_ids
        return len(valid) / len(opponent_ledger)
