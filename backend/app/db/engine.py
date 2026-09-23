"""SQLAlchemy engine for PostgreSQL."""

from functools import lru_cache

from sqlalchemy import URL, Engine, create_engine, text

from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    url = URL.create(
        drivername="postgresql+psycopg",
        username=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
    )
    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": int(settings.health_timeout_seconds)},
    )


def ping_postgres(engine: Engine) -> None:
    """Raise if PostgreSQL cannot answer a trivial query."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
