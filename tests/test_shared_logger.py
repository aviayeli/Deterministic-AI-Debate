"""Phase 13 — Shared RotatingFileHandler logger and v1.0.0 versioning."""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from src.debate.shared.logger import get_logger
from src.debate.shared.version import __version__


def test_version_is_1_0_0() -> None:
    assert __version__ == "1.0.0"


def test_get_logger_returns_logger(tmp_path: Path) -> None:
    logger = get_logger("returns", log_dir=tmp_path)
    assert isinstance(logger, logging.Logger)


def test_get_logger_creates_log_file(tmp_path: Path) -> None:
    logger = get_logger("creates", log_dir=tmp_path)
    logger.info("hello")
    assert any(tmp_path.iterdir())


def test_log_file_contains_message(tmp_path: Path) -> None:
    logger = get_logger("contains", log_dir=tmp_path)
    logger.info("sentinel_xyz")
    logs = list(tmp_path.glob("*.log"))
    assert logs
    assert "sentinel_xyz" in logs[0].read_text()


def test_handler_max_bytes_is_50000(tmp_path: Path) -> None:
    logger = get_logger("maxbytes", log_dir=tmp_path)
    rfh = next(h for h in logger.handlers if isinstance(h, logging.handlers.RotatingFileHandler))
    assert rfh.maxBytes == 50_000


def test_handler_backup_count_is_20(tmp_path: Path) -> None:
    logger = get_logger("backupct", log_dir=tmp_path)
    rfh = next(h for h in logger.handlers if isinstance(h, logging.handlers.RotatingFileHandler))
    assert rfh.backupCount == 20


def test_log_format_includes_level_and_name(tmp_path: Path) -> None:
    logger = get_logger("logfmt", log_dir=tmp_path)
    logger.warning("check_format")
    content = next(tmp_path.glob("*.log")).read_text()
    assert "WARNING" in content
    assert "logfmt" in content


def test_get_logger_same_name_no_handler_duplication(tmp_path: Path) -> None:
    a = get_logger("dupcheck", log_dir=tmp_path)
    b = get_logger("dupcheck", log_dir=tmp_path)
    assert a is b
    rfh_count = sum(1 for h in a.handlers if isinstance(h, logging.handlers.RotatingFileHandler))
    assert rfh_count == 1


def test_logger_exposes_standard_levels(tmp_path: Path) -> None:
    logger = get_logger("levels", log_dir=tmp_path)
    logger.debug("d")
    logger.info("i")
    logger.warning("w")
    logger.error("e")


def test_log_dir_is_created_if_missing(tmp_path: Path) -> None:
    nested = tmp_path / "new" / "subdir"
    get_logger("newdir", log_dir=nested)
    assert nested.is_dir()


def test_rotation_creates_backup_file(tmp_path: Path) -> None:
    logger = get_logger("rotates", log_dir=tmp_path)
    big_msg = "x" * 1_000
    for _ in range(60):
        logger.info(big_msg)
    for h in logger.handlers:
        if isinstance(h, logging.handlers.RotatingFileHandler):
            h.close()
    logs = list(tmp_path.glob("*.log*"))
    assert len(logs) >= 2


def test_gatekeeper_has_shared_logger() -> None:
    import src.debate.gatekeeper.gatekeeper as gk_mod

    assert isinstance(gk_mod._logger, logging.Logger)


def test_watchdog_has_shared_logger() -> None:
    import src.debate.gatekeeper.watchdog as wd_mod

    assert isinstance(wd_mod._logger, logging.Logger)
