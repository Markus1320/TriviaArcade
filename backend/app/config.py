"""Application settings, read from environment variables."""

from functools import lru_cache

from pydantic import SecretStr
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

    # Random walk for question seeds, see app/graph/walk.py. top_share is the share of
    # each entity type, most famous first, that walks may visit (1.0 = all).
    walk_min_hops: int = 1
    walk_max_hops: int = 2
    walk_top_share: float = 0.5

    # Seconds to wait when probing a database for the health endpoint.
    health_timeout_seconds: float = 5.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
