"""Seed demo accounts without modifying existing balances."""

from sqlalchemy.dialects.postgresql import insert

from banking.config import get_settings
from banking.infrastructure.database import make_engine
from banking.infrastructure.models import Account

DEMO_ACCOUNTS = {
    "A1001": 1000,
    "A1002": 800,
}


def main() -> None:
    accounts = [
        {
            "account_id": account_id,
            "opening_balance_minor": balance,
            "balance_minor": balance,
        }
        for account_id, balance in DEMO_ACCOUNTS.items()
    ]

    engine = make_engine(get_settings())

    try:
        with engine.begin() as connection:
            statement = insert(Account).values(accounts)
            statement = statement.on_conflict_do_nothing(index_elements=[Account.account_id])
            connection.execute(statement)
    finally:
        engine.dispose()

    print("Demo accounts ensured. Existing balances unchanged.")


if __name__ == "__main__":
    main()
