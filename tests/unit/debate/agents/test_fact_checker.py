"""Tests for FactCheckerSubagent — all offline via injected mock search tool."""
from unittest.mock import MagicMock

from src.debate.agents.fact_checker import OBJECTION_PREFIX, FactCheckerSubagent


def _mock_search(snippet: str) -> MagicMock:
    tool = MagicMock()
    tool.search.return_value = snippet
    return tool


def _agent_mock(claim_text: str) -> MagicMock:
    msg = MagicMock()
    msg.content = [MagicMock(text='{"claim_text":"LLM claim","addressed_claim_ids":[]}')]
    msg.usage = MagicMock(input_tokens=10, output_tokens=5)
    return msg


def test_check_returns_none_when_search_is_empty():
    fc = FactCheckerSubagent(search_tool=_mock_search(""))
    assert fc.check("AI replaces engineers") is None


def test_check_returns_none_when_no_contradiction_markers():
    fc = FactCheckerSubagent(search_tool=_mock_search("AI is advancing rapidly in many fields."))
    assert fc.check("AI will replace engineers") is None


def test_check_returns_snippet_when_contradiction_found():
    snippet = "Actually, contrary to popular belief, this is incorrect."
    fc = FactCheckerSubagent(search_tool=_mock_search(snippet))
    result = fc.check("AI will replace all software engineers by 2025")
    assert result == snippet


def test_check_is_case_insensitive_for_markers():
    snippet = "ACTUALLY, this claim is MISLEADING and false claim."
    fc = FactCheckerSubagent(search_tool=_mock_search(snippet))
    assert fc.check("some claim") is not None


def test_check_returns_none_for_neutral_snippet():
    fc = FactCheckerSubagent(search_tool=_mock_search("AI automation is growing."))
    assert fc.check("AI is growing") is None


def test_format_objection_starts_with_prefix():
    fc = FactCheckerSubagent(search_tool=_mock_search(""))
    result = fc.format_objection("Some proof.", "My base claim.")
    assert result.startswith(OBJECTION_PREFIX)


def test_format_objection_contains_proof_and_base_claim():
    fc = FactCheckerSubagent(search_tool=_mock_search(""))
    result = fc.format_objection("The proof snippet.", "My argument here.")
    assert "The proof snippet." in result
    assert "My argument here." in result


def test_objection_prefix_constant_is_correct():
    assert OBJECTION_PREFIX == "**OBJECTION! Fake News!**"


def test_pro_agent_prepends_objection_when_fact_check_fires():
    from src.debate.agents.pro import ProAgent
    from src.debate.schemas.claim import ClaimPayloadSchema
    from src.debate.schemas.round import LedgerEntry

    snippet = "contrary to what was claimed, this is incorrect data."
    fc = FactCheckerSubagent(search_tool=_mock_search(snippet))
    gk = MagicMock()
    gk.call.return_value = MagicMock(
        content=[MagicMock(text='{"claim_text":"My argument","addressed_claim_ids":[]}')],
        usage=MagicMock(input_tokens=10, output_tokens=5),
    )
    opponent_claim = ClaimPayloadSchema(
        agent_id="CON", round_number=1, stance="CON",
        claim_text="AI will definitely replace all engineers", addressed_claim_ids=[],
    )
    opponent_ledger = [LedgerEntry(claim=opponent_claim)]
    agent = ProAgent(gk, fact_checker=fc)
    claim = agent.generate_claim(1, opponent_ledger)

    assert claim.claim_text.startswith(OBJECTION_PREFIX)
    assert "My argument" in claim.claim_text


def test_pro_agent_skips_objection_when_no_contradiction():
    from src.debate.agents.pro import ProAgent
    from src.debate.schemas.claim import ClaimPayloadSchema
    from src.debate.schemas.round import LedgerEntry

    fc = FactCheckerSubagent(search_tool=_mock_search("AI is advancing."))
    gk = MagicMock()
    gk.call.return_value = MagicMock(
        content=[MagicMock(text='{"claim_text":"My argument","addressed_claim_ids":[]}')],
        usage=MagicMock(input_tokens=10, output_tokens=5),
    )
    opponent_claim = ClaimPayloadSchema(
        agent_id="CON", round_number=1, stance="CON",
        claim_text="Some neutral claim", addressed_claim_ids=[],
    )
    agent = ProAgent(gk, fact_checker=fc)
    claim = agent.generate_claim(1, [LedgerEntry(claim=opponent_claim)])
    assert not claim.claim_text.startswith(OBJECTION_PREFIX)


def test_con_agent_prepends_objection_when_fact_check_fires():
    from src.debate.agents.con import ConAgent
    from src.debate.schemas.claim import ClaimPayloadSchema
    from src.debate.schemas.round import LedgerEntry

    snippet = "This is misleading — actually contrary to evidence."
    fc = FactCheckerSubagent(search_tool=_mock_search(snippet))
    gk = MagicMock()
    gk.call.return_value = MagicMock(
        content=[MagicMock(text='{"claim_text":"Counter argument","addressed_claim_ids":[]}')],
        usage=MagicMock(input_tokens=10, output_tokens=5),
    )
    opponent_claim = ClaimPayloadSchema(
        agent_id="PRO", round_number=1, stance="PRO",
        claim_text="AI replaces 80% of engineers already", addressed_claim_ids=[],
    )
    agent = ConAgent(gk, fact_checker=fc)
    claim = agent.generate_claim(1, [LedgerEntry(claim=opponent_claim)])
    assert claim.claim_text.startswith(OBJECTION_PREFIX)


def test_fact_checker_skips_when_no_opponent_ledger():
    from src.debate.agents.pro import ProAgent

    fc = FactCheckerSubagent(search_tool=_mock_search("definitely incorrect"))
    gk = MagicMock()
    gk.call.return_value = MagicMock(
        content=[MagicMock(text='{"claim_text":"Arg","addressed_claim_ids":[]}')],
        usage=MagicMock(input_tokens=10, output_tokens=5),
    )
    agent = ProAgent(gk, fact_checker=fc)
    claim = agent.generate_claim(1, [])
    assert not claim.claim_text.startswith(OBJECTION_PREFIX)
    fc._search.search.assert_not_called()
