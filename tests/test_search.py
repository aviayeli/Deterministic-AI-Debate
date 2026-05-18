"""Tests for WebSearchTool — all offline, no real network calls."""
import json
import urllib.error
from unittest.mock import MagicMock, patch

from src.debate.tools.search import WebSearchTool


def _mock_resp(body: str) -> MagicMock:
    m = MagicMock()
    m.__enter__ = lambda s: s
    m.__exit__ = MagicMock(return_value=False)
    m.read.return_value = body.encode()
    return m


def test_search_returns_abstract_text():
    data = json.dumps({"AbstractText": "AI automates code review.", "RelatedTopics": []})
    with patch("urllib.request.urlopen", return_value=_mock_resp(data)):
        assert WebSearchTool().search("AI software") == "AI automates code review."


def test_search_falls_back_to_empty_string_on_network_error():
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
        assert WebSearchTool().search("query") == ""


def test_search_falls_back_to_empty_string_on_json_error():
    with patch("urllib.request.urlopen", return_value=_mock_resp("not-json")):
        assert WebSearchTool().search("query") == ""


def test_search_uses_related_topics_when_abstract_is_empty():
    data = json.dumps({"AbstractText": "", "RelatedTopics": [{"Text": "Related snippet."}]})
    with patch("urllib.request.urlopen", return_value=_mock_resp(data)):
        assert WebSearchTool().search("query") == "Related snippet."


def test_search_returns_empty_when_both_abstract_and_related_missing():
    data = json.dumps({"AbstractText": "", "RelatedTopics": []})
    with patch("urllib.request.urlopen", return_value=_mock_resp(data)):
        assert WebSearchTool().search("query") == ""


def test_search_tool_injects_facts_into_pro_agent_prompt():
    from src.debate.agents.pro import ProAgent

    mock_tool = MagicMock()
    mock_tool.search.return_value = "Fact: AI tripled productivity."
    gk = MagicMock()
    gk.call.return_value = MagicMock(
        content=[MagicMock(text='{"claim_text":"x","addressed_claim_ids":[]}')],
        usage=MagicMock(input_tokens=10, output_tokens=5),
    )
    agent = ProAgent(gk, search_tool=mock_tool)
    agent.generate_claim(1, [])

    mock_tool.search.assert_called_once()
    call_kwargs = gk.call.call_args.kwargs
    user_content = call_kwargs["messages"][0]["content"]
    assert "Fact: AI tripled productivity." in user_content


def test_search_tool_injects_facts_into_con_agent_prompt():
    from src.debate.agents.con import ConAgent

    mock_tool = MagicMock()
    mock_tool.search.return_value = "Fact: creativity resists automation."
    gk = MagicMock()
    gk.call.return_value = MagicMock(
        content=[MagicMock(text='{"claim_text":"y","addressed_claim_ids":[]}')],
        usage=MagicMock(input_tokens=10, output_tokens=5),
    )
    agent = ConAgent(gk, search_tool=mock_tool)
    agent.generate_claim(1, [])

    call_kwargs = gk.call.call_args.kwargs
    user_content = call_kwargs["messages"][0]["content"]
    assert "Fact: creativity resists automation." in user_content


def test_search_is_fetched_only_once_across_rounds():
    from src.debate.agents.pro import ProAgent

    mock_tool = MagicMock()
    mock_tool.search.return_value = "cached fact"
    gk = MagicMock()
    gk.call.return_value = MagicMock(
        content=[MagicMock(text='{"claim_text":"x","addressed_claim_ids":[]}')],
        usage=MagicMock(input_tokens=10, output_tokens=5),
    )
    agent = ProAgent(gk, search_tool=mock_tool)
    agent.generate_claim(1, [])
    agent.generate_claim(2, [])

    assert mock_tool.search.call_count == 1


def test_agent_works_without_search_tool():
    from src.debate.agents.pro import ProAgent

    gk = MagicMock()
    gk.call.return_value = MagicMock(
        content=[MagicMock(text='{"claim_text":"x","addressed_claim_ids":[]}')],
        usage=MagicMock(input_tokens=10, output_tokens=5),
    )
    agent = ProAgent(gk)
    claim = agent.generate_claim(1, [])
    assert claim.claim_text == "x"
