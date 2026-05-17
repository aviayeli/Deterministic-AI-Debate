from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    RECENCY_DECAY_LAMBDA: float = 0.3
    V1_DISTANCE_THRESHOLD: float = 0.4
    CENTROID_ALIGNMENT_THRESHOLD: float = 0.7
    ANTHROPIC_API_KEY: str = ""
    MAX_ROUNDS: int = 10
    BENCHMARK_RUNS: int = 5
    LEDGER_WINDOW: int = 3
    LLM_MODEL: str = "claude-sonnet-4-6"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    MAX_WORKERS: int = 4
    ASSETS_DIR: str = "assets/"


settings = Settings()
