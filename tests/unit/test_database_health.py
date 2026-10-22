"""Readiness SQL must be bounded without altering the banking schema."""

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, cast

from pydantic import SecretStr
from sqlalchemy.engine import Engine

from banking.config import Settings
from banking.infrastructure import database


class FakeConnection:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def execute(self, statement: Any, _params: Any = None) -> None:
        self.commands.append(str(statement))


class FakeEngine:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self) -> None:
        self.connection = FakeConnection()

    @contextmanager
    def begin(self):
        yield self.connection


def test_ready_probe_limits_sql_waits_before_write() -> None:
    engine = FakeEngine()
    database.probe_committed_write(cast(Engine, engine), "banking-b")
    assert "statement_timeout" in engine.connection.commands[0]
    assert "lock_timeout" in engine.connection.commands[1]
    assert "INSERT INTO health_probes" in engine.connection.commands[2]


def test_engine_bounds_pool_and_statement_waits(monkeypatch) -> None:
    captured = {}

    def fake_create_engine(_url, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(database, "create_engine", fake_create_engine)
    settings = Settings(
        database_url=SecretStr("postgresql+psycopg://user:secret@localhost/banking"),
        db_statement_timeout_ms=7000,
        db_pool_timeout=4,
    )
    database.make_engine(settings)
    assert captured["pool_timeout"] == 4
    assert captured["connect_args"]["options"] == "-c statement_timeout=7000"
