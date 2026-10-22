"""Create one isolated simulated account for manual failover demonstrations."""

import argparse
from uuid import uuid4

from sqlalchemy import insert

from banking.config import get_settings
from banking.infrastructure.database import make_engine
from banking.infrastructure.models import Account


def create_account(account_id: str, balance: int) -> None:
    if not account_id.startswith("DEMO_") or len(account_id) > 64:
        raise ValueError("Account ID must start with DEMO_ and be at most 64 characters")
    if not 0 <= balance <= 10**12:
        raise ValueError("Opening balance must be between 0 and 10**12")

    engine = make_engine(get_settings())
    try:
        with engine.begin() as connection:
            connection.execute(
                insert(Account).values(
                    account_id=account_id,
                    opening_balance_minor=balance,
                    balance_minor=balance,
                )
            )
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", default=f"DEMO_{uuid4().hex[:20]}")
    parser.add_argument("--balance", type=int, default=1000)
    parser.add_argument("--acknowledge-writes", action="store_true")
    args = parser.parse_args()

    if not args.acknowledge_writes:
        parser.error("Pass --acknowledge-writes to create a simulated account")

    create_account(args.account, args.balance)
    print(f"Created {args.account} with opening balance {args.balance}")


if __name__ == "__main__":
    main()
