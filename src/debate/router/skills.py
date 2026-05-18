"""Topic-driven Router: selects skill instructions once per debate to avoid context bloat."""

_SKILL_LIBRARY: dict[str, str] = {
    "causal": "Explain causal chains; avoid presenting correlation as causation.",
    "economic": "Frame arguments in economic terms: cost, efficiency, and labor markets.",
    "ethical": "Address ethical dimensions: fairness, autonomy, and societal impact.",
    "historical": "Draw upon historical precedents and analogies from past tech shifts.",
    "statistical": "Prioritize empirical data, statistics, and peer-reviewed studies.",
    "technical": "Emphasize technical depth, architectural trade-offs, and domain knowledge.",
}

_KEYWORD_SKILL_MAP: list[tuple[list[str], str]] = [
    (["engineer", "software", "code", "program", "developer"], "technical"),
    (["replace", "job", "employ", "work", "labor", "automat", "workforce"], "economic"),
    (["data", "statistic", "percent", "survey", "study", "research"], "statistical"),
    (["ethic", "fair", "right", "moral", "society", "human", "bias"], "ethical"),
    (["history", "past", "previous", "industri", "revolution", "wave"], "historical"),
    (["cause", "lead to", "result", "because", "since", "therefore"], "causal"),
]

_DEFAULT_SKILLS: frozenset[str] = frozenset({"economic", "technical"})


class TopicRouter:
    """Runs once at debate start; maps topic keywords to context-efficient skill snippets."""

    def route(self, topic: str) -> str:
        """Return skill instructions relevant to *topic*, defaulting to economic+technical."""
        lower = topic.lower()
        selected = {
            skill
            for keywords, skill in _KEYWORD_SKILL_MAP
            if any(kw in lower for kw in keywords)
        }
        if not selected:
            selected = set(_DEFAULT_SKILLS)
        instructions = "\n".join(
            f"- {_SKILL_LIBRARY[s]}" for s in sorted(selected) if s in _SKILL_LIBRARY
        )
        return f"Skill guidelines for this debate:\n{instructions}"
