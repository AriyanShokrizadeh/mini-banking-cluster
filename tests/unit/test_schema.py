"""New databases can be initialized safely without changing existing data."""

import pytest
from scripts.setup.init_schema import create_schema
from sqlalchemy import create_engine, inspect, text

from banking.infrastructure.models import Account


def test_new_database_gets_all_banking_tables() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        create_schema(engine)
        assert set(inspect(engine).get_table_names()) == set(Account.metadata.tables)
    finally:
        engine.dispose()


def test_existing_database_is_not_modified() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE existing_data (value INTEGER)"))
            connection.execute(text("INSERT INTO existing_data VALUES (42)"))

        with pytest.raises(RuntimeError, match="Database is not empty"):
            create_schema(engine)

        with engine.connect() as connection:
            assert connection.scalar(text("SELECT value FROM existing_data")) == 42
        assert inspect(engine).get_table_names() == ["existing_data"]
    finally:
        engine.dispose()
