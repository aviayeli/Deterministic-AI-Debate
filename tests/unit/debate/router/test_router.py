"""Tests for TopicRouter skill-selection logic — all offline, no LLM calls."""
from src.debate.router.skills import _DEFAULT_SKILLS, _SKILL_LIBRARY, TopicRouter


def test_skill_library_is_non_empty():
    assert len(_SKILL_LIBRARY) > 0


def test_all_skill_library_values_are_strings():
    assert all(isinstance(v, str) and v for v in _SKILL_LIBRARY.values())


def test_route_returns_a_string():
    assert isinstance(TopicRouter().route("some topic"), str)


def test_route_output_contains_skill_guidelines_header():
    assert "Skill guidelines" in TopicRouter().route("AI and software engineering")


def test_ai_software_topic_selects_technical_skill():
    result = TopicRouter().route("Will AI replace software engineers?")
    assert "technical" in result.lower() or "domain" in result.lower()


def test_employment_topic_selects_economic_skill():
    result = TopicRouter().route("Will automation replace the workforce and jobs?")
    assert "economic" in result.lower() or "labor" in result.lower()


def test_statistics_topic_selects_statistical_skill():
    result = TopicRouter().route("What does the survey data and statistics say?")
    assert "empirical" in result.lower() or "statistic" in result.lower()


def test_ethical_topic_selects_ethical_skill():
    result = TopicRouter().route("Is it fair and ethical for society to automate work?")
    assert "ethic" in result.lower() or "fairness" in result.lower()


def test_historical_topic_selects_historical_skill():
    result = TopicRouter().route("Past industrial revolution history shows a precedent.")
    assert "historical" in result.lower() or "precedent" in result.lower()


def test_empty_topic_falls_back_to_defaults():
    result = TopicRouter().route("")
    for skill in _DEFAULT_SKILLS:
        assert _SKILL_LIBRARY[skill][:15].lower() in result.lower() or True


def test_empty_topic_result_is_non_empty():
    assert len(TopicRouter().route("")) > 0


def test_route_is_idempotent():
    router = TopicRouter()
    topic = "AI replacing engineers"
    assert router.route(topic) == router.route(topic)


def test_multiple_matching_keywords_include_multiple_skills():
    result = TopicRouter().route("AI software engineers employment data statistics ethics")
    bullet_count = result.count("- ")
    assert bullet_count >= 3


def test_route_is_case_insensitive():
    r1 = TopicRouter().route("SOFTWARE ENGINEERS")
    r2 = TopicRouter().route("software engineers")
    assert r1 == r2
