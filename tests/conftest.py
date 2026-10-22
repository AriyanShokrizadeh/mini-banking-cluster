"""Shared SQLite fixtures for local tests (not distributed YSQL verification)."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from banking.infrastructure.database import Base
from banking.infrastructure.models import Account
from banking.main import create_app
from tests.helpers import IsolatedSettings


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)

    with Session(engine) as session, session.begin():
        session.add(Account(account_id="A1001", opening_balance_minor=1000, balance_minor=1000))

    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    app = create_app(IsolatedSettings(database_url=None), engine=engine)
    with TestClient(app) as test_client:
        yield test_client
