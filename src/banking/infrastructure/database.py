"""Database engine configuration and connectivity checks."""

from sqlalchemy import text
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase

from banking.config import Settings


class Base(DeclarativeBase):
    """Shared SQLAlchemy metadata for the banking tables."""


def make_engine(settings: Settings) -> Engine:
    database_url = settings.database_url
    if database_url is None:
        raise RuntimeError("BANKING_DATABASE_URL is not configured")

    return create_engine(
        database_url.get_secret_value(),
        pool_pre_ping=True,
        isolation_level="SERIALIZABLE",
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        connect_args={
            "connect_timeout": settings.db_connect_timeout,
            "options": f"-c statement_timeout={settings.db_statement_timeout_ms}",
        },
    )


def check_ysql_connection(engine: Engine) -> None:
    """Check connectivity; this does not verify that writes can commit."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def probe_committed_write(engine: Engine, instance_name: str) -> None:
    """Prove a commit with a bounded SQL statement and lock wait."""
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("SET LOCAL statement_timeout = '6s'"))
            connection.execute(text("SET LOCAL lock_timeout = '2s'"))
        connection.execute(
            text("""
                INSERT INTO health_probes (instance_name, sequence)
                VALUES (:instance, 1)
                ON CONFLICT (instance_name)
                DO UPDATE SET sequence = health_probes.sequence + 1
            """),
            {"instance": instance_name},
        )
