import json
from dataclasses import dataclass
from pathlib import Path

_CONFIG_PATH = Path(__file__).parents[3] / "config" / "rate_limits.json"


@dataclass
class GatekeeperConfig:
    requests_per_minute: int
    max_retries: int
    timeout_seconds: float
    backoff_factor: float
    retryable_status_codes: list[int]
    queue_maxsize: int
    max_workers: int = 4

    @classmethod
    def load(cls, path: Path = _CONFIG_PATH) -> "GatekeeperConfig":
        data = json.loads(path.read_text())
        return cls(**data)
