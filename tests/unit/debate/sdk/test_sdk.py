"""Phase 6a — DebateSDK public facade."""
from pathlib import Path
from unittest.mock import MagicMock, patch

_SDK = "src.debate.sdk.sdk"
_ANTH = f"{_SDK}.anthropic.Anthropic"
_GK = f"{_SDK}.ApiGatekeeper"
_GK_CFG = f"{_SDK}.GatekeeperConfig.load"
_PRO = f"{_SDK}.ProAgent"
_CON = f"{_SDK}.ConAgent"
_RUN_DEBATE = f"{_SDK}.run_debate"
_RUN_BENCH = f"{_SDK}.run_benchmarks"
_REPORTER = f"{_SDK}.BenchmarkReporter.export"
_ANALYSIS = f"{_SDK}.analysis.generate_all"


def _make_sdk(topic=None):
    with patch(_ANTH), patch(_GK), patch(_GK_CFG):
        from src.debate.sdk import DebateSDK
        return DebateSDK(topic=topic)


def test_sdk_instantiates_without_error() -> None:
    sdk = _make_sdk()
    assert sdk is not None


def test_sdk_uses_default_topic_when_none_given() -> None:
    sdk = _make_sdk()
    assert isinstance(sdk._topic, str) and sdk._topic


def test_sdk_stores_custom_topic() -> None:
    sdk = _make_sdk(topic="custom topic")
    assert sdk._topic == "custom topic"


def test_topic_passed_to_agents_on_run_single() -> None:
    with (
        patch(_ANTH), patch(_GK), patch(_GK_CFG),
        patch(_PRO) as mock_pro,
        patch(_CON) as mock_con,
        patch(_RUN_DEBATE, return_value=MagicMock()),
    ):
        from src.debate.sdk import DebateSDK
        sdk = DebateSDK(topic="custom topic")
        sdk.run_single(max_rounds=3)
    _, pro_kw = mock_pro.call_args
    _, con_kw = mock_con.call_args
    assert pro_kw.get("topic") == "custom topic"
    assert con_kw.get("topic") == "custom topic"


def test_run_single_calls_run_debate_once() -> None:
    with (
        patch(_ANTH), patch(_GK), patch(_GK_CFG),
        patch(_RUN_DEBATE, return_value=MagicMock()) as mock_rd,
    ):
        from src.debate.sdk import DebateSDK
        DebateSDK().run_single(max_rounds=3)
    mock_rd.assert_called_once()


def test_run_benchmark_delegates_to_run_benchmarks() -> None:
    with (
        patch(_ANTH), patch(_GK), patch(_GK_CFG),
        patch(_RUN_BENCH, return_value=[MagicMock(), MagicMock()]) as mock_rb,
    ):
        from src.debate.sdk import DebateSDK
        result = DebateSDK().run_benchmark(n=2, max_rounds=3)
    mock_rb.assert_called_once()
    assert len(result) == 2


def test_export_delegates_to_reporter() -> None:
    with (
        patch(_ANTH), patch(_GK), patch(_GK_CFG),
        patch(_REPORTER) as mock_exp,
    ):
        from src.debate.sdk import DebateSDK
        sdk = DebateSDK()
        sdk.export([MagicMock()], "out.json")
    mock_exp.assert_called_once()
    called_path = mock_exp.call_args[0][1]
    assert str(called_path).endswith("out.json")


def test_generate_analysis_delegates_to_analysis_module() -> None:
    with (
        patch(_ANTH), patch(_GK), patch(_GK_CFG),
        patch(_ANALYSIS, return_value=[Path("a.png")]) as mock_gen,
    ):
        from src.debate.sdk import DebateSDK
        DebateSDK().generate_analysis("data.json", "assets/")
    mock_gen.assert_called_once()


def test_sdk_public_api_is_complete() -> None:
    sdk = _make_sdk()
    for method in ("run_single", "run_benchmark", "export", "generate_analysis", "set_topic"):
        assert callable(getattr(sdk, method)), f"SDK missing method: {method}"


def test_main_has_no_internal_imports() -> None:
    """main.py must route exclusively through DebateSDK — no direct submodule imports."""
    main_src = (Path(__file__).parents[4] / "main.py").read_text()
    for forbidden in ("pipeline", "BenchmarkReporter", "run_benchmarks", "reporter"):
        assert forbidden not in main_src, (
            f"main.py imports '{forbidden}' directly — must route through DebateSDK"
        )


def test_run_benchmark_passes_max_rounds() -> None:
    """DebateSDK.run_benchmark(n, max_rounds) must forward max_rounds to run_benchmarks()."""
    with (
        patch(_ANTH), patch(_GK), patch(_GK_CFG),
        patch(_RUN_BENCH, return_value=[]) as mock_rb,
    ):
        from src.debate.sdk import DebateSDK
        DebateSDK().run_benchmark(n=2, max_rounds=5)
    _, kw = mock_rb.call_args
    assert kw.get("max_rounds") == 5, "max_rounds not forwarded to run_benchmarks()"
