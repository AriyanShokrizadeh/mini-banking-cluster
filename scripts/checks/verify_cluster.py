"""Verify YugabyteDB topology, schema, and optional write readiness."""

import argparse
import sys

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from banking.config import get_settings
from banking.infrastructure.database import make_engine, probe_committed_write
from banking.infrastructure.models import Account


def verify_topology(connection: Connection, expected_nodes: int) -> None:
    nodes = connection.execute(text("SELECT host, zone, node_type FROM yb_servers()")).all()

    hosts = {node.host for node in nodes}
    zones = {node.zone for node in nodes}

    if len(hosts) != expected_nodes:
        raise RuntimeError(f"Expected {expected_nodes} nodes, found {len(hosts)}")

    if len(zones) != expected_nodes:
        raise RuntimeError("Nodes must be in distinct zones")

    if any(node.node_type != "primary" for node in nodes):
        raise RuntimeError("Non-primary node detected")

    isolation = connection.scalar(text("SHOW transaction_isolation"))

    if isolation is None or isolation.lower() != "serializable":
        raise RuntimeError(f"Expected serializable isolation, got {isolation}")

    print(f"Topology: {expected_nodes} primary nodes in distinct zones")
    print("Transaction isolation: serializable")


def verify_schema(connection: Connection) -> None:
    """Check the tables and columns expected by the current models."""
    inspector = inspect(connection)
    expected = Account.metadata.tables
    missing = set(expected) - set(inspector.get_table_names())
    if missing:
        raise RuntimeError(f"Missing tables: {', '.join(sorted(missing))}")

    for table in expected.values():
        present = {column["name"] for column in inspector.get_columns(table.name)}
        missing_columns = set(table.columns.keys()) - present
        if missing_columns:
            raise RuntimeError(
                f"Missing columns in {table.name}: {', '.join(sorted(missing_columns))}"
            )

    print("Schema: required tables and columns verified")


def inspect_cluster(
    *,
    expected_nodes: int,
    schema: bool,
    write_probe: bool,
) -> None:
    engine = make_engine(get_settings())

    try:
        with engine.connect() as connection:
            verify_topology(connection, expected_nodes)

            if schema:
                verify_schema(connection)

        if write_probe:
            probe_committed_write(engine, "phase5-verify")
            print("Committed write probe: success")
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nodes", type=int, default=3)
    parser.add_argument("--schema", action="store_true")
    parser.add_argument("--write-probe", action="store_true")

    args = parser.parse_args()

    if args.nodes < 1:
        parser.error("--nodes must be positive")

    try:
        inspect_cluster(
            expected_nodes=args.nodes,
            schema=args.schema,
            write_probe=args.write_probe,
        )
    except Exception as exc:
        print(
            f"Cluster verification failed: {type(exc).__name__}",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
