"""Application settings, read from environment variables."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str
    postgres_password: SecretStr
    postgres_db: str

    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr

    # Optional so the stack starts without an API key; the LLM factory checks them when used.
    ollama_api_key: SecretStr | None = None
    ollama_base_url: str | None = None
    llm_generator_model: str | None = None
    llm_judge_model: str | None = None
    llm_timeout_seconds: float = 120.0

    # Random walk for question seeds, see app/graph/walk.py.
    walk_min_hops: int = 1
    walk_max_hops: int = 2
    # How strongly a hop avoids entities with many relations (0 = not at all).
    walk_hub_penalty: float = Field(default=0.5, ge=0)
    # 1UPs, see app/game/rules.py: correct answers in a row for one, the most a player can
    # hold, and how many a new run starts with.
    life_combo: int = Field(default=3, ge=1)
    max_lives: int = Field(default=3, ge=0)
    start_lives: int = Field(default=1, ge=0)
    # Start entities of the last this many questions (of all runs) are not used again.
    recent_starts_blocked: int = Field(default=300, ge=0)

    # Time limit per question in seconds, counted from when the question is shown. 0 = off.
    answer_time_seconds: int = Field(default=30, ge=0)

    # Seconds to wait when probing a database for the health endpoint.
    health_timeout_seconds: float = 5.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
