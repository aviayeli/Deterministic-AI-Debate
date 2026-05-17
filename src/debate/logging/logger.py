import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_CONFIG_PATH = Path(__file__).parents[3] / "config" / "logging_config.json"


@dataclass
class LoggingConfig:
    log_dir: str
    max_files: int
    max_lines: int
    log_level: str
    log_format: str
    date_format: str

    @classmethod
    def load(cls) -> "LoggingConfig":
        data = json.loads(_CONFIG_PATH.read_text())
        return cls(**data)


_config: LoggingConfig | None = None


def _get_config() -> LoggingConfig:
    global _config
    if _config is None:
        _config = LoggingConfig.load()
    return _config


class FifoRotatingHandler(logging.Handler):
    """File handler that rotates on line count and evicts oldest files (FIFO)."""

    def __init__(self, config: LoggingConfig) -> None:
        super().__init__()
        self._cfg = config
        self._lock = threading.Lock()
        self._log_dir = Path(config.log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._handle = None
        self._lines: int = 0
        self._counter: int = 0
        self._open_new_file()

    def _open_new_file(self) -> None:
        if self._handle is not None:
            self._handle.close()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = self._log_dir / f"debate_{ts}_{self._counter:04d}.log"
        self._handle = path.open("a", encoding="utf-8")
        self._lines = 0
        self._counter += 1
        self._enforce_fifo()

    def _enforce_fifo(self) -> None:
        files = sorted(self._log_dir.glob("*.log"))  # lexicographic = chronological
        while len(files) > self._cfg.max_files:
            files.pop(0).unlink(missing_ok=True)

    def emit(self, record: logging.LogRecord) -> None:
        with self._lock:
            if self._lines >= self._cfg.max_lines:
                self._open_new_file()
            self._handle.write(self.format(record) + "\n")
            self._handle.flush()
            self._lines += 1

    def close(self) -> None:
        with self._lock:
            if self._handle is not None:
                self._handle.close()
                self._handle = None
        super().close()


_loggers: dict[str, "DebateLogger"] = {}


class DebateLogger:
    def __init__(self, name: str, config: LoggingConfig | None = None) -> None:
        cfg = config or _get_config()
        self._logger = logging.getLogger(f"debate.{name}")
        if self._logger.handlers:
            return
        self._logger.setLevel(getattr(logging, cfg.log_level))
        self._logger.propagate = False
        fmt = logging.Formatter(cfg.log_format, datefmt=cfg.date_format)
        fh = FifoRotatingHandler(cfg)
        fh.setFormatter(fmt)
        self._logger.addHandler(fh)
        sh = logging.StreamHandler()
        sh.setLevel(logging.WARNING)
        sh.setFormatter(fmt)
        self._logger.addHandler(sh)

    def debug(self, msg: str, **kwargs) -> None:
        self._logger.debug(msg, **kwargs)

    def info(self, msg: str, **kwargs) -> None:
        self._logger.info(msg, **kwargs)

    def warning(self, msg: str, **kwargs) -> None:
        self._logger.warning(msg, **kwargs)

    def error(self, msg: str, **kwargs) -> None:
        self._logger.error(msg, **kwargs)


def get_logger(name: str) -> "DebateLogger":
    if name not in _loggers:
        _loggers[name] = DebateLogger(name)
    return _loggers[name]
