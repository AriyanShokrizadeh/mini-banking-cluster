"""Real, read-only topology checks. Opt-in with a disposable cluster URL."""

import os

import pytest
from scripts.checks.verify_cluster import verify_topology
from sqlalchemy import create_engine

pytestmark = pytest.mark.cluster


def test_three_primary_nodes_and_serializable_isolation() -> None:
    url = os.getenv("BANKING_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set BANKING_TEST_DATABASE_URL to opt in")
    if not url.startswith("postgresql+psycopg://"):
        pytest.fail("A YugabyteDB YSQL psycopg URL is required")

    engine = create_engine(url, isolation_level="SERIALIZABLE", pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            verify_topology(connection, expected_nodes=3)
    finally:
        engine.dispose()
