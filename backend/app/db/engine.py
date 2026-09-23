"""SQLAlchemy engine and sessions for PostgreSQL."""

from functools import lru_cache

from sqlalchemy import URL, Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings


def database_url(settings: Settings) -> URL:
    return URL.create(
        drivername="postgresql+psycopg",
        username=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
    )


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        database_url(settings),
        pool_pre_ping=True,
        connect_args={"connect_timeout": int(settings.health_timeout_seconds)},
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def ping_postgres(engine: Engine) -> None:
    """Raise if PostgreSQL cannot answer a trivial query."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
