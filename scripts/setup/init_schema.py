"""Create banking tables once in a new, empty database; never upgrade existing tables."""

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from banking.config import get_settings
from banking.infrastructure.database import make_engine
from banking.infrastructure.models import Account


def create_schema(engine: Engine) -> None:
    existing = inspect(engine).get_table_names()
    if existing:
        raise RuntimeError(
            f"Database is not empty ({', '.join(sorted(existing))}). "
            "Use a fresh database; existing schemas are never modified."
        )

    Account.metadata.create_all(engine, checkfirst=False)


def main() -> None:
    engine = make_engine(get_settings())
    try:
        create_schema(engine)
    finally:
        engine.dispose()
    print("Banking schema created. Run seed_demo.py to add demo accounts.")


if __name__ == "__main__":
    main()
