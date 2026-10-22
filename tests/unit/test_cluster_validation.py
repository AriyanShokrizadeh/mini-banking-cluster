"""Validate node topology and database structure."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from scripts.checks.verify_cluster import verify_schema, verify_topology
from sqlalchemy import text
from sqlalchemy.engine import Engine


def test_three_primary_nodes_in_distinct_zones_are_accepted() -> None:
    connection = Mock()
    connection.execute.return_value.all.return_value = [
        SimpleNamespace(host=f"node-{n}", zone=f"zone-{n}", node_type="primary") for n in range(3)
    ]
    connection.scalar.return_value = "serializable"

    verify_topology(connection, expected_nodes=3)


def test_insufficient_nodes_are_rejected() -> None:
    connection = Mock()
    connection.execute.return_value.all.return_value = [
        SimpleNamespace(host="node-1", zone="zone-1", node_type="primary")
    ]

    with pytest.raises(RuntimeError, match="Expected 3 nodes"):
        verify_topology(connection, expected_nodes=3)


def test_complete_database_schema_is_accepted(engine: Engine) -> None:
    with engine.connect() as connection:
        verify_schema(connection)


def test_missing_database_table_is_rejected(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE operations"))
        with pytest.raises(RuntimeError, match="Missing tables: operations"):
            verify_schema(connection)


def test_missing_database_column_is_rejected(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE health_probes"))
        connection.execute(
            text("CREATE TABLE health_probes (instance_name VARCHAR(64) PRIMARY KEY)")
        )
        with pytest.raises(RuntimeError, match="Missing columns in health_probes: sequence"):
            verify_schema(connection)
