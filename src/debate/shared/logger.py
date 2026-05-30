"""Centralized RotatingFileHandler logger for the debate system."""
from __future__ import annotations

import json
import logging
import logging.handlers
from pathlib import Path

_DEFAULT_LOG_DIR = Path("logs")
_CONFIG_PATH = Path(__file__).parents[3] / "config" / "logging_config.json"
_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

_cache: dict[str, logging.Logger] = {}


def _load_config(config_path: Path) -> tuple[int, int]:
    data = json.loads(config_path.read_text())
    return data["max_bytes"], data["backup_count"]


def get_logger(
    name: str,
    log_dir: Path | str | None = None,
    config_path: Path | str | None = None,
) -> logging.Logger:
    """Return a named logger backed by a RotatingFileHandler; idempotent."""
    resolved = Path(log_dir) if log_dir is not None else _DEFAULT_LOG_DIR
    key = f"{name}:{resolved}"
    if key in _cache:
        return _cache[key]
    resolved.mkdir(parents=True, exist_ok=True)
    cfg = Path(config_path) if config_path is not None else _CONFIG_PATH
    max_bytes, backup_count = _load_config(cfg)
    logger = logging.getLogger(f"debate.shared.{name}")
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        fmt = logging.Formatter(_FORMAT)
        rfh = logging.handlers.RotatingFileHandler(
            resolved / f"{name}.log",
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
            delay=True,
        )
        rfh.setFormatter(fmt)
        logger.addHandler(rfh)
    _cache[key] = logger
    return logger
