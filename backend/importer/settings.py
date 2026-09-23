"""Environment settings for the importer (Neo4j connection only)."""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root when running from source (backend/importer/settings.py -> repo root).
# Inside the container the package lives in /app/importer, so this resolves to "/",
# where config/ and data/ are mounted.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ImporterSettings(BaseSettings):
    # On the host, the .env file in the repository root provides the Neo4j credentials.
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr
