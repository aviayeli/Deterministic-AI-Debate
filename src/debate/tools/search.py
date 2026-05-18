import json
import urllib.error
import urllib.parse
import urllib.request

_DDG_URL = "https://api.duckduckgo.com/"
_TIMEOUT = 5


class WebSearchTool:
    """Fetches a fact snippet from DuckDuckGo instant answers (no API key required).

    Falls back to '' on any network or parse failure so agents degrade gracefully
    in offline or CI environments.
    """

    def search(self, query: str) -> str:
        """Return a short text snippet relevant to *query*, or '' on failure."""
        try:
            params = urllib.parse.urlencode({
                "q": query,
                "format": "json",
                "no_html": "1",
                "skip_disambig": "1",
            })
            with urllib.request.urlopen(
                f"{_DDG_URL}?{params}", timeout=_TIMEOUT
            ) as resp:
                data = json.loads(resp.read().decode())
            return data.get("AbstractText") or self._from_related(data)
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            return ""

    @staticmethod
    def _from_related(data: dict) -> str:
        topics = data.get("RelatedTopics", [])
        if topics and isinstance(topics[0], dict):
            return topics[0].get("Text", "")
        return ""
