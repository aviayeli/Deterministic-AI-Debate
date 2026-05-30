"""Phase 4 — TDD: FIFO rotating logger."""
import logging
import threading
import uuid
from pathlib import Path

from src.debate.logging import get_logger
from src.debate.logging.logger import DebateLogger, LoggingConfig


def _cfg(tmp_path: Path, max_files: int = 5, max_lines: int = 10) -> LoggingConfig:
    return LoggingConfig(
        log_dir=str(tmp_path),
        max_files=max_files,
        max_lines=max_lines,
        log_level="DEBUG",
        log_format="%(asctime)s | %(levelname)-8s | %(name)-12s | %(message)s",
        date_format="%Y-%m-%dT%H:%M:%S",
    )


def _name() -> str:
    return f"t_{uuid.uuid4().hex[:8]}"


def test_get_logger_returns_debate_logger() -> None:
    assert isinstance(get_logger("factory_check"), DebateLogger)


def test_get_logger_same_name_same_instance() -> None:
    n = _name()
    assert get_logger(n) is get_logger(n)


def test_config_loads_from_json() -> None:
    cfg = LoggingConfig.load()
    assert cfg.max_files == 20
    assert cfg.max_lines == 500
    assert cfg.log_dir == "logs/"


def test_has_all_log_methods(tmp_path: Path) -> None:
    logger = DebateLogger(_name(), config=_cfg(tmp_path))
    for m in ("debug", "info", "warning", "error"):
        assert callable(getattr(logger, m))


def test_log_dir_created_on_init(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b"
    DebateLogger(_name(), config=_cfg(nested))
    assert nested.exists()


def test_file_created_after_info(tmp_path: Path) -> None:
    logger = DebateLogger(_name(), config=_cfg(tmp_path))
    logger.info("hello")
    assert len(list(tmp_path.glob("*.log"))) == 1


def test_message_written_to_file(tmp_path: Path) -> None:
    logger = DebateLogger(_name(), config=_cfg(tmp_path))
    logger.info("unique_xyz_marker")
    content = next(tmp_path.glob("*.log")).read_text()
    assert "unique_xyz_marker" in content


def test_log_format_has_level_and_timestamp(tmp_path: Path) -> None:
    logger = DebateLogger(_name(), config=_cfg(tmp_path))
    logger.info("fmt_test")
    content = next(tmp_path.glob("*.log")).read_text()
    assert "INFO" in content
    assert "T" in content  # ISO timestamp separator (e.g. 2026-05-17T14:30:22)


def test_no_handler_duplication(tmp_path: Path) -> None:
    n = _name()
    c = _cfg(tmp_path)
    DebateLogger(n, config=c)
    DebateLogger(n, config=c)
    assert len(logging.getLogger(f"debate.{n}").handlers) == 2


def test_rotation_creates_second_file(tmp_path: Path) -> None:
    logger = DebateLogger(_name(), config=_cfg(tmp_path, max_lines=5))
    for i in range(6):
        logger.info(f"line {i}")
    assert len(list(tmp_path.glob("*.log"))) == 2


def test_old_file_has_max_lines_after_rotation(tmp_path: Path) -> None:
    logger = DebateLogger(_name(), config=_cfg(tmp_path, max_lines=5))
    for i in range(6):
        logger.info(f"line {i}")
    files = sorted(tmp_path.glob("*.log"))
    assert len(files[0].read_text().splitlines()) == 5


def test_fifo_eviction_deletes_oldest(tmp_path: Path) -> None:
    logger = DebateLogger(_name(), config=_cfg(tmp_path, max_files=3, max_lines=2))
    for i in range(7):
        logger.info(f"line {i}")
    assert len(list(tmp_path.glob("*.log"))) <= 3


def test_fifo_never_exceeds_max_files(tmp_path: Path) -> None:
    logger = DebateLogger(_name(), config=_cfg(tmp_path, max_files=3, max_lines=2))
    for i in range(20):
        logger.info(f"line {i}")
    assert len(list(tmp_path.glob("*.log"))) <= 3


def test_concurrent_writes_no_errors(tmp_path: Path) -> None:
    logger = DebateLogger(_name(), config=_cfg(tmp_path, max_files=20, max_lines=500))
    errors: list[Exception] = []

    def _write() -> None:
        try:
            for i in range(50):
                logger.info(f"line {i}")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_write) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    total = sum(len(f.read_text().splitlines()) for f in tmp_path.glob("*.log"))
    assert total == 500
