import re

DISCOURSE_POLICY = (
    "DEBATE CIVILITY POLICY — enforced deterministically by the Judge:\n"
    "1. Agents MUST use respectful, professional language at all times.\n"
    "2. Personal attacks, insults, and profanity are strictly prohibited.\n"
    "3. Arguments must be evidence-based; derogatory stereotypes are forbidden.\n"
    "4. Inflammatory language that demeans any person or group is a violation.\n"
    "5. Each distinct violation incurs a 0.05 score deduction (max 0.25 total).\n"
    "Policy is applied post-debate to preserve benchmark reproducibility."
)

_VIOLATIONS: list[str] = [
    r"\bidiot\b",
    r"\bstupid\b",
    r"\bmoron\b",
    r"\bdumb\b",
    r"\bfool(ish)?\b",
    r"\bworthless\b",
    r"\buseless\b",
    r"\bshut\s+up\b",
    r"\bdisgusting\b",
    r"\bimbecile\b",
    r"\bpathetic\b",
]

_PENALTY_PER_VIOLATION = 0.05
_MAX_PENALTY = 0.25


class DiscourseChecker:
    """Enforces DISCOURSE_POLICY and returns a deterministic score deduction."""

    def __init__(self) -> None:
        self._patterns = [re.compile(p, re.IGNORECASE) for p in _VIOLATIONS]

    def penalty(self, text: str) -> float:
        """Return a deduction in [0.0, _MAX_PENALTY]; 0.0 means no violations."""
        hits = sum(1 for p in self._patterns if p.search(text))
        return min(hits * _PENALTY_PER_VIOLATION, _MAX_PENALTY)

    def violations(self, text: str) -> list[str]:
        """Return the regex patterns that matched in *text*."""
        return [p.pattern for p in self._patterns if p.search(text)]
