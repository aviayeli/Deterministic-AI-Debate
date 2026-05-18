"""FactCheckerSubagent: checks opponent claims for misinformation via web search."""
from typing import Any

OBJECTION_PREFIX = "**OBJECTION! Fake News!**"

_CONTRADICTION_MARKERS = [
    "actually,",
    "contrary to",
    "debunked",
    "false claim",
    "incorrect",
    "misleading",
    "myth",
    "not true",
]


class FactCheckerSubagent:
    """Searches the web for counter-evidence against an opponent's claim.

    Inject a mock *search_tool* in tests; the default uses ``WebSearchTool``.
    """

    def __init__(self, search_tool: Any = None) -> None:
        if search_tool is None:
            from ..tools.search import WebSearchTool
            search_tool = WebSearchTool()
        self._search = search_tool

    def check(self, claim_text: str) -> str | None:
        """Return a proof snippet if the claim appears contradicted, else ``None``.

        Triggers when the search result contains a recognized contradiction marker.
        """
        snippet = self._search.search(claim_text[:120])
        if snippet and any(m in snippet.lower() for m in _CONTRADICTION_MARKERS):
            return snippet
        return None

    def format_objection(self, proof: str, base_claim: str) -> str:
        """Prepend the standard objection prefix + proof before *base_claim*."""
        return f"{OBJECTION_PREFIX} {proof}\n\n{base_claim}"
